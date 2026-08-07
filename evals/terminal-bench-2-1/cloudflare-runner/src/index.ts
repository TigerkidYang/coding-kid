import { Container, getContainer } from "@cloudflare/containers";

interface Env {
  BENCHMARK_TRIAL: DurableObjectNamespace<BenchmarkTrialContainer>;
  CODING_KID_BENCH_API_KEY: string;
  CODING_KID_BENCH_BASE_URL: string;
}

export class BenchmarkTrialContainer extends Container {
  defaultPort = 8080;
  requiredPorts = [8080];
  sleepAfter = "2h";
  enableInternet = true;
}

function authorized(request: Request, env: Env): boolean {
  return request.headers.get("authorization") === `Bearer ${env.CODING_KID_BENCH_API_KEY}`;
}

function validId(value: string): boolean {
  return /^[a-z0-9][a-z0-9-]{0,62}$/.test(value);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (!authorized(request, env)) {
      return Response.json({ error: "unauthorized" }, { status: 401 });
    }

    const url = new URL(request.url);
    const match = url.pathname.match(
      /^\/trials\/([^/]+)(?:\/(start|preflight|docker-smoke|status|stop))?$/,
    );
    if (!match || !validId(match[1])) {
      return Response.json({ error: "not_found" }, { status: 404 });
    }

    const trialId = match[1];
    const action = match[2] ?? "status";
    const container = getContainer(env.BENCHMARK_TRIAL, trialId);
    if (action === "stop") {
      await container.stop();
      return Response.json({ stopped: true, trial_id: trialId });
    }
    await container.startAndWaitForPorts({
      ports: [8080],
      startOptions: {
        envVars: {
          CODING_KID_BENCH_API_KEY: env.CODING_KID_BENCH_API_KEY,
          CODING_KID_BENCH_BASE_URL: env.CODING_KID_BENCH_BASE_URL,
          BENCHMARK_TRIAL_ID: trialId,
        },
      },
    });

    const target = new URL(`http://container/${action}`);
    return container.fetch(new Request(target, request));
  },
} satisfies ExportedHandler<Env>;
