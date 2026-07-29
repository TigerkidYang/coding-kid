def moving_average(xs, window=3):
    if window <= 0:
        raise ValueError("window")
    out = []
    for i in range(len(xs)):
        start = max(0, i - window + 1)
        out.append(sum(xs[start:i + 1]) / (i - start + 1))
    return out
