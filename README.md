# GeekTrend

默认中文 · [English](README.en.md)

[📊 打开在线数据看板](https://lurui1997.github.io/GeekTrend/) · [GitHub Trending](https://github.com/trending/) · [使用说明](docs/USAGE.md)

[![Capture GitHub Trending](https://github.com/lurui1997/GeekTrend/actions/workflows/snapshot.yml/badge.svg)](https://github.com/lurui1997/GeekTrend/actions/workflows/snapshot.yml)
[![Publish Pages Report](https://github.com/lurui1997/GeekTrend/actions/workflows/pages.yml/badge.svg)](https://github.com/lurui1997/GeekTrend/actions/workflows/pages.yml)
![Python 3.13](https://img.shields.io/badge/Python-3.13-blue)
![GitHub Trending](https://img.shields.io/badge/source-GitHub%20Trending-24292f)
![Schedule](https://img.shields.io/badge/schedule-every%202h-2ea44f)
![Timezone](https://img.shields.io/badge/timezone-UTC%2B08%3A00-orange)
![AI Agent Analysis](https://img.shields.io/badge/analysis-AI%20agent%20contributors-purple)
![GitHub Pages](https://img.shields.io/badge/report-GitHub%20Pages-0969da)

## 为什么做 GeekTrend

GitHub 项目里越来越常见 bot 和 AI agent 的贡献痕迹。在
[GitHub Trending](https://github.com/trending/) 上，这个信号尤其有价值：Trending
项目代表开发者正在真实构建、发布、协作和获得关注的方向。

GeekTrend 把这些公开活动沉淀成一份 **agent contribute 榜**。它不是问开发者“你喜欢哪个
coding agent”，而是观察哪些 agent 真实出现在热门项目的 contributor 列表里。也就是说，
如果 `claude`、`codex`、`cursor`、`github-copilot` 或其他 agent 反复出现在当前项目中，
这比问卷或营销口径更接近开发者真实的 agent 选型。

每份快照都会保存当时的 Trending 仓库，并补充一组尽力而为的 contributor 分析：

- 是否出现已知 AI coding agent contributor，例如 `claude`、`codex`、`cursor`、
  `github-copilot` 或 `copilot`；
- 根据公开 GitHub profile 信号推断项目来源国家/地区；
- 统计当前快照中使用 AI agent contributor 的项目占比。

## GeekTrend 做了什么
GeekTrend 每 2 小时抓取一次 GitHub Trending，保存不可变快照，并分析热门项目的 AI agent contributor 使用情况。在线看板：

> [https://lurui1997.github.io/GeekTrend/](https://lurui1997.github.io/GeekTrend/)

看板会展示最新快照里的：

- AI agent 项目占比；
- Agent contributor 排行；
- Trending 项目来源国家/地区分布；
- 每个 Trending 仓库的语言、介绍、contributors 和分析结果。


## 快速理解

| 你关心的问题 | GeekTrend 给出的答案 |
|---|---|
| 哪些 agent 更常出现在 contributor 里？ | 看在线看板的 Agent 排行 |
| 项目主要来自哪些国家/地区？ | 看来源分布图和 `来源` |
| 数据是否会自动更新？ | 会。采集 workflow 每 2 小时运行一次；成功发布快照后，Pages 看板自动重建 |
| 原始数据保存在哪里？ | `data/YYYY/MM/DD/*.json` |

## 数据流程

下面的饼图来自第一次带分析能力的 live smoke run：当时 11 个 Trending 项目里，有 8 个项目检测到已知 AI agent contributor。
之后每份快照都会保存自己的 `ai_agent_project_count` 和 `ai_agent_project_ratio`。

```mermaid
flowchart LR
    A["GitHub Actions<br/>每 2 小时"] --> B["抓取 GitHub Trending<br/>All languages · Daily"]
    B --> C["解析仓库<br/>名称 · 链接 · contributors · 描述 · 语言"]
    C --> D["分析 contributors<br/>AI agent 使用 · 来源信号"]
    D --> E["写入不可变 JSON<br/>UTC+08:00 路径"]
    E --> F["提交单个快照<br/>data/YYYY/MM/DD/*.json"]
    F --> G["更新 GitHub Pages<br/>可视化报表"]
```

```mermaid
pie title Snapshot AI Agent Adoption
    "使用 AI agent contributor" : 8
    "未检测到 AI agent contributor" : 3
```



## 本地运行

项目需要 Python 3.13。创建隔离环境并安装锁定依赖：

```sh
python3.13 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.lock
```

采集到当前仓库，或指定临时目录做 smoke test：

```sh
python -m geektrend.cli
python -m geektrend.cli --output-root /tmp/geektrend-smoke
```

命令会输出创建的相对路径。快照使用 UTC+08:00 时间，路径格式为：

```text
data/YYYY/MM/DD/YYYY-MM-DDTHH-MM-SS+08-00.json
```

查看本地最新快照：

```sh
find data -type f -name '*.json' | sort | tail -1
```

运行离线测试：

```sh
python -m pytest -q
```

更完整的操作步骤、快照查看命令和排障说明见 [docs/USAGE.md](docs/USAGE.md)。


## 自动化

`Capture GitHub Trending` GitHub Actions workflow 每 2 小时运行一次，也可以在 GitHub Actions
页面手动触发。GitHub schedule 是 best effort，所以延迟或跳过的运行不会回填。

workflow 会：

1. checkout 仓库；
2. 安装锁定的 Python 依赖；
3. 运行离线测试；
4. 采集当前 GitHub Trending 页面；
5. 使用 `GITHUB_TOKEN` 补充 contributor profile 分析；
6. 把一个新快照文件提交回分支。
7. 触发 `Publish Pages Report` workflow，重新生成并发布
   [GitHub Pages 在线报表](https://lurui1997.github.io/GeekTrend/)。

为了让 workflow 能提交快照，需要在 GitHub 仓库里开启：

```text
Settings → Actions → General → Workflow permissions → Read and write permissions
```

## 注意事项

workflow 使用一个 concurrency group 串行化运行，不会取消正在执行的采集。发布步骤会有限重试 push
竞争，但永远不会覆盖或回填已有快照路径；每个成功发布的快照都视为不可变数据。

GitHub 没有官方 Trending API。本项目解析公开 Trending HTML，所以 GitHub markup 变化可能导致采集失败；
失败时不会生成快照。Contributor enrichment 使用公开 GitHub profile 数据；当 profile 信号缺失或 API
请求失败时，会降级为 `unknown`。测试使用本地 fixtures，不依赖网络。

写入器使用 hard link 原子发布快照以保证 no-overwrite 行为。因此 output root 和临时文件必须位于支持
hard link 的文件系统上。
