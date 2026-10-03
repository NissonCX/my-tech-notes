#!/usr/bin/env python3
"""ollama 推理性能实测：TTFT / TPOT / 吞吐

为什么必须用【流式】：只有流式才能测到真实的 TTFT —— 第一个 chunk 到达的时刻。
非流式拿到的那组耗时字段里，prompt_eval_duration 只是 prefill 的计算耗时，
不含排队和首包，会低估 TTFT。

⚠️ thinking：qwen3.5 这类模型默认开思考，token 会全部落进 `thinking` 字段而
`response` 为空。本脚本默认 `think=false` 保证实验干净，同时兼容开启的情况。

用法：
    python3 bench_ollama.py -m qwen3.5:9b                     # 默认 1K / 4K / 16K
    python3 bench_ollama.py -m qwen3.5:9b -c 1024 4096        # 指定输入长度
    python3 bench_ollama.py -m qwen3.5:9b -g 300 --think      # 开思考，单独统计
"""
import argparse
import json
import statistics
import time
import urllib.request

API = "http://localhost:11434/api/generate"


def one_run(model, prompt, num_predict, num_ctx=None, think=False):
    opts = {"num_predict": num_predict, "temperature": 0}   # 温度 0 = 可复现
    if num_ctx:
        opts["num_ctx"] = num_ctx
    body = json.dumps({
        "model": model, "prompt": prompt, "stream": True,
        "think": think, "options": opts,
    }).encode()
    req = urllib.request.Request(API, data=body,
                                 headers={"Content-Type": "application/json"})

    t0 = time.perf_counter()
    ttft = None
    stamps = []
    n_think = n_resp = 0
    final = {}
    with urllib.request.urlopen(req, timeout=1800) as r:
        for line in r:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            th, rs = d.get("thinking") or "", d.get("response") or ""
            if th or rs:
                now = time.perf_counter()
                if ttft is None:
                    ttft = now - t0          # ★ 真实 TTFT：第一个 chunk 到达
                stamps.append(now)
                n_think += 1 if th else 0
                n_resp += 1 if rs else 0
            if d.get("done"):
                final = d
                break

    n = len(stamps)
    if n < 2:
        raise RuntimeError(f"只收到 {n} 个 chunk（n_think={n_think}, n_resp={n_resp}）"
                           f"，无法算 TPOT —— 调大 -g，或检查模型是否支持 think 参数")
    tpot = statistics.mean(b - a for a, b in zip(stamps, stamps[1:]))
    wall = stamps[-1] - t0
    eval_count = final.get("eval_count", 0)
    eval_s = final.get("eval_duration", 0) / 1e9
    return {
        "ttft": ttft, "tpot": tpot, "tokens": n,
        "n_think": n_think, "n_resp": n_resp,
        "wall": wall,
        # 纯 decode 速度（不含 TTFT）；之前用 tokens/wall 会把首字等待也算进去
        "decode_tps": eval_count / eval_s if eval_s else 0.0,
        "prompt_count": final.get("prompt_eval_count", 0),
        "cached": final.get("prompt_eval_cached_count", 0),
        "api_eval_count": eval_count,
        # API 自报的 prefill 耗时（不含排队/首包，可与 TTFT 对照）
        "api_prefill_s": final.get("prompt_eval_duration", 0) / 1e9,
        "api_load_s": final.get("load_duration", 0) / 1e9,
    }


def filler(n):
    """造一段大致 n 个 token 的填充文本（真实 token 数以 API 回报为准）。"""
    return " ".join(f"w{i}" for i in range(int(n / 1.3)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-m", "--model", required=True)
    ap.add_argument("-c", "--contexts", type=int, nargs="+", default=[1024, 4096, 16384])
    ap.add_argument("-g", "--gen", type=int, default=150, help="每档生成多少 token")
    ap.add_argument("--think", action="store_true", help="开启思考（默认关闭）")
    a = ap.parse_args()

    print(f"模型 {a.model}｜生成 {a.gen} token｜temperature 0｜think={a.think}\n")
    print("预热中（首次加载模型，不计入结果）…")
    one_run(a.model, "你好", 16, num_ctx=4096, think=a.think)

    print(f"\n{'目标输入':>8} {'实际输入':>8} {'TTFT(s)':>9} {'prefill(s)':>11} "
          f"{'TPOT(ms)':>9} {'decode(t/s)':>12} {'think':>6} {'resp':>5} {'缓存':>5}")
    print("-" * 88)
    for ctx in a.contexts:
        prompt = filler(ctx) + "\n\n继续随便写点东西。"
        r = one_run(a.model, prompt, a.gen,
                    num_ctx=max(ctx + a.gen + 1024, 8192), think=a.think)
        print(f"{ctx:>8} {r['prompt_count']:>8} {r['ttft']:>9.3f} {r['api_prefill_s']:>11.3f} "
              f"{r['tpot']*1000:>9.1f} {r['decode_tps']:>12.1f} "
              f"{r['n_think']:>6} {r['n_resp']:>5} {r['cached']:>5}")

    print("\n读表：TTFT 应随输入【线性增长】（prefill 是 compute-bound）；")
    print("      TPOT 基本不变，但吞吐会随上下文变厚而下降（decode 是 memory-bound）。")


if __name__ == "__main__":
    main()
