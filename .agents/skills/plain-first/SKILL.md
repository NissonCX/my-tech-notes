---
name: plain-first
description: Explain an unfamiliar technical concept, concrete-first. Use when the user is learning a topic, asks what something really is, or restates an idea and wants a verdict.
---

# plain-first

Explain a concept so it lands the first time, then make it stick.

## The three beats

Every new term gets all three, in this order:

> **【先讲人话】** an analogy or a tiny concrete case, zero jargon.
> **【专业名词】** the Chinese term, plus its English.
> **【定义】** one sentence saying what the thing *is*, not what it does.

The analogy carries the intuition. The term is the word the user will say out loud later, in a doc or an interview.

## Running a session

1. **Name the broken premise first.** Locate which assumption in what the user just said is wrong, and say so before explaining anything. A correct explanation aimed at the wrong premise slides off.
2. **One rung per turn.** The user restates what they understood; that restatement is the input to the next rung. Slower than feels necessary is the right speed.
3. **Verdict every restatement.** Lead with ✅ / ⚠️ / ❌ per claim, then name the *specific word* that slipped — "扰动" → "确定性的结构化信号", "自我训练" → "训练时调整权重". A verdict at the level of "不太对" is useless.
4. **Shrink the numbers until they're checkable.** 4096 dims → 2. 32 layers → 3. The user then verifies the mechanism by hand instead of trusting the prose.
5. **Anchor to their world.** Close each concept by naming where it shows up in the work they are heading toward.
6. **End with two or three self-check questions**, answerable from what was just taught.

## One metaphor, held

Give each topic a single physical metaphor and reuse it verbatim throughout: a meeting room where every floor keeps its own sign-in book; 32 hospital departments passing one chart along; a conveyor belt that only ever gets annotated; a library versus a desk.

Swapping metaphors mid-topic resets the user's footing.

## Register

The user is heading into professional work on the topic, so hand them the sentence they would say in that room:

> "decode 阶段是 memory-bound 的，瓶颈在 KV cache 的显存带宽，不在算力。"
