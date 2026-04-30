# vc-outreach-agent

[English](README.md) | **中文**

> Solo Founder OS 第 3 个 agent —— 找投资人,基于(投资人 × 项目)用 Claude 起草个性化冷启动邮件,通过 markdown HITL 队列管理回复。**永远不自动发送。** 永远是你审、你按发送。

[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/vc-outreach-agent.svg)](https://pypi.org/project/vc-outreach-agent/)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](#)
[![Model](https://img.shields.io/badge/Claude-Sonnet_4.6-D97706?logoColor=white)](https://anthropic.com)

作者 [Alex Ji](https://github.com/alex-jb) —— 单人独立开发者,在做 [Orallexa](https://github.com/alex-jb/orallexa-ai-trading-agent) 和 [VibeXForge](https://github.com/alex-jb/vibex)。这工具诞生于这一句:

> *表格里 50 个投资人。手写 50 封个性化冷启动 = 10 小时。50 个人发同一封模板 = 0 回复。一定有更好的默认值。*

## 它干什么

```
investors.csv  +  project.yml
                  ↓
              Claude(Sonnet 4.6,prompt 强制反水货约束)
                  ↓
              queue/pending/<时间戳>-<项目>-to-<投资人>.md
                  ↓
        ┌────────────────────────────────┐
        │  你在 Obsidian 里审稿           │
        │  (改 / 批准 / 拒绝)             │
        └────────────────────────────────┘
                  ↓
              queue/approved/  →  v0.2 SMTP 发送
              queue/rejected/  →  归档,不发
```

Drafter 的 prompt 强制以下规则,**违反 → fallback 到 template**:

1. 第一句必须是一条**具体**的、把投资人的 thesis 跟项目串起来的话。"I follow your work" 这种废话直接 ban。
2. 第 2-3 句:**先 traction,后 vision**。一个数字、一个 ship 出来的东西、一个需求信号。
3. 第 4 句:**一个**具体的 ask。"15 分钟通话" —— 永远不是"任何想法都欢迎"。
4. 正文 < 110 词,标题 < 8 词。
5. **禁词**(硬性):synergy, disrupting, passionate, leverage, innovative, cutting-edge, revolutionize, "I'd love to", "circle back", "touch base", "thought leader", "in the AI space", "exciting opportunity"。
6. 语气:平等对话,简洁,不用感叹号,不用 emoji。

## 安装

```bash
git clone https://github.com/alex-jb/vc-outreach-agent.git
cd vc-outreach-agent
pip install -e .
cp .env.example .env  # 填好 ANTHROPIC_API_KEY
```

## 使用

```bash
# 1. 写一次项目描述
cat > orallexa.yml <<EOF
name: Orallexa
one_liner: AI 量化交易 agent
stage: pre-seed
raise_amount: \$500k
...
EOF

# 2. 把投资人列在 CSV 里(列:name,email,firm,role,thesis_hint,linkedin,twitter,notes)
#    thesis_hint 这一列最关键 —— 这是让每封邮件感觉真的写给他的关键

# 3. 批量起草进队列
vc-outreach-agent draft --project orallexa.yml --investors investors.csv

# 4. 审稿 at ~/.vc-outreach-agent/queue/pending/
#    Obsidian 里打开每个 .md,改完移到:
#      ../approved/  发出
#      ../rejected/  不发
```

## 冷启动邮件为什么必须 HITL

自动发冷邮件是 category error。两个原因:

1. **一封烂邮件毁的不止这轮。** 投资人圈子小,会传话。一封自动发的、对不上号的邮件不仅这轮黄,下轮你都进不去。
2. **真正起作用的那 1% 个性化来自你的上下文,不是 Claude 的。** "嘿,我看到你 led 了 X 这轮,我现在需要的就是这套打法。" Claude 不知道你 IRL 跟谁见过,但你知道。

v0.1 只入队。v0.2 加 SMTP 发送(仍然要你手动移文件)。v0.5 可能加低风险 follow-up 的自动发送,但**冷启动第一封永远 HITL**。

## Roadmap

- [x] **v0.1** —— Drafter(LLM + template fallback) · markdown HITL 队列 · CSV/YAML 输入 · 14 tests
- [x] **v0.2** —— SMTP 发送(给 `queue/approved/`)· 支持 Gmail/Postmark/Resend/Sendgrid · 干跑模式 · 25 tests
- [ ] **v0.3** —— 投资人 enrichment(Twitter / LinkedIn 抓)· 自动 build thesis_hint
- [ ] **v0.4** —— 多触点 follow-up(T+5 天、T+12 天)逐步降低 conviction
- [ ] **v0.5** —— Pipeline 分析:打开率 / 回复率 / 见面率,按 thesis_hint pattern 切

## 协议

MIT。
