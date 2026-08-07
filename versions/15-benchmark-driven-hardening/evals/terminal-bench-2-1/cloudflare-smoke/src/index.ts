import { Container, getContainer } from "@cloudflare/containers";

interface Env {
  BENCHMARK_SMOKE: DurableObjectNamespace<BenchmarkSmokeContainer>;
}

export class BenchmarkSmokeContainer extends Container {
  defaultPort = 8080;
  requiredPorts = [8080];
  sleepAfter = "5m";
  enableInternet = true;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname !== "/" && url.pathname !== "/health") {
      return Response.json({ error: "not_found" }, { status: 404 });
    }

    const container = getContainer(env.BENCHMARK_SMOKE, "smoke");
    return container.fetch(new Request("http://container/health", request));
  },
} satisfies ExportedHandler<Env>;
