#!/usr/bin/env python3
"""KV Cache 显存估算器

公式（阶段 0 学的五因子）：
    总字节 = token数 × (KV头数 × 每头维度) × 2 × 层数 × 每数字节
             └─ 行数 ─┘ └──── 宽度 ────┘   ↑      ↑        ↑
                                        K和V   层数   fp16 = 2

用法：
    python3 kv_calc.py                                    # 默认：那道练习题
    python3 kv_calc.py --preset llama3-8b -t 10000
    python3 kv_calc.py --preset llama3-8b -t 10000 -k 4   # 假装改成 GQA-4
    python3 kv_calc.py -l 28 -k 4 -d 128 -t 128000        # 全手填
"""
import argparse

# 常见配置（数值以各模型官方 config 为准，这里只作起点）
PRESETS = {
    "llama3-8b":  dict(layers=32, kv_heads=8,  head_dim=128),
    "llama3-70b": dict(layers=80, kv_heads=8,  head_dim=128),
    "qwen2.5-7b": dict(layers=28, kv_heads=4,  head_dim=128),
    "mha-32h":    dict(layers=32, kv_heads=32, head_dim=128),  # 对照：不做 GQA 的老配置
}


def kv_bytes(tokens, layers, kv_heads, head_dim, bytes_per=2):
    """返回 KV Cache 总字节数。"""
    width = kv_heads * head_dim          # 每行多宽
    per_layer = tokens * width * 2       # ×2：K 一份、V 一份
    return per_layer * layers * bytes_per


def human(n):
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if n < 1024:
            return f"{n:.2f} {unit}"
        n /= 1024
    return f"{n:.2f} PiB"


def main():
    ap = argparse.ArgumentParser(description="KV Cache 显存估算")
    ap.add_argument("--preset", choices=sorted(PRESETS), help="用预设配置")
    ap.add_argument("-t", "--tokens", type=int, default=10000, help="token 数（行数）")
    ap.add_argument("-l", "--layers", type=int, help="层数")
    ap.add_argument("-k", "--kv-heads", type=int, help="KV 头数（决定宽度）")
    ap.add_argument("-d", "--head-dim", type=int, help="每头维度")
    ap.add_argument("-b", "--bytes-per", type=int, default=2, help="每数字节：fp16=2, fp32=4")
    a = ap.parse_args()

    cfg = PRESETS.get(a.preset, {}) if a.preset else {}
    layers = a.layers or cfg.get("layers") or 32
    kv_heads = a.kv_heads or cfg.get("kv_heads") or 8
    head_dim = a.head_dim or cfg.get("head_dim") or 128

    width = kv_heads * head_dim
    n = kv_bytes(a.tokens, layers, kv_heads, head_dim, a.bytes_per)

    print(f"配置    : {layers} 层 ｜ KV {kv_heads} 头 × {head_dim} 维 = 宽度 {width}")
    print(f"行数    : {a.tokens:,} token")
    print(f"每数字节: {a.bytes_per}（fp16）")
    print("-" * 46)
    print(f"K+V/层  : {a.tokens * width * 2:,} 个数")
    print(f"× {layers} 层 : {a.tokens * width * 2 * layers:,} 个数")
    print(f"× {a.bytes_per} 字节 : {n:,} 字节")
    print(f"KV Cache = {human(n)}")


if __name__ == "__main__":
    main()
