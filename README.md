# trip-map-builder · 出游信息地图生成器

把截图、手打清单、地图收藏夹或文章中的地点信息整理为可交互的地图页面：**真实地图 + 独立滚动清单 + 搜索筛选 + 来源截图 + 一键复制 + 直线距离**。

本项目提供两种使用方式：

- **Agent Skill**：按 [SKILL.md](SKILL.md) 整理素材、核对地点，再生成地图。
- **Python CLI**：已有 `trip.json` 和 `data.json` 时直接构建，不需要 Agent 或地图检索连接器。

输出 HTML 内联 CSS、JavaScript、Leaflet 和地点数据，无需前端安装或打包。**底图瓦片需要联网；来源图片是独立资源，需与页面一起保留。**

## 先看效果

[开封美食地图在线案例](https://fang-123559.github.io/henan-kaifeng/) · [案例源码](https://github.com/fang-123559/henan-kaifeng)

开封项目是通用引擎成型前的手工案例，可用于了解页面功能，不是本引擎当前输出的逐字对应版本。本引擎生成 Leaflet 清单地图；不包含《汴京食帖》的视觉测试生成器。

## 快速开始：已有数据

### 环境

| 操作 | 条件 |
|---|---|
| 校验与构建 | Python 3；`assets/build.py` 仅使用标准库 |
| 查看成品 | 浏览器；在线底图需网络，截图需保留对应资源目录 |
| 浏览器探针 | Chrome；自动检测 Windows 常见路径，或使用系统可找到的 `chrome` 命令 |
| 网页定位 | HTTPS 或 localhost，并获得浏览器授权 |

浏览器探针的其他平台兼容性未系统验证。CLI 不包含 OCR、商户自动检索或坐标系自动转换，这些属于素材准备与核验步骤。

### 运行开封样例

```bash
git clone https://github.com/fang-123559/trip-map-builder.git
cd trip-map-builder

# 只校验数据与配置，不生成文件，也不检查来源图片
python assets/build.py --trip examples/kaifeng/trip.json --check-only

# 生成页面
python assets/build.py --trip examples/kaifeng/trip.json --out examples/kaifeng/index.html
```

校验通过会输出 `✓ 校验通过（未生成文件）`。生成成功会输出文件路径，以及本样例的口径：

```text
条目 217 ＝ 精确 113 + 区域近似 70 + 未定位 34 + 不标注 0 ｜ 星标 1 ｜ 类别 11 组 / 46 型
```

打开 `examples/kaifeng/index.html` 查看。**样例不附来源截图**：构建会提示 215 条图片引用全部找不到；这是已说明的样例告警，截图详情不可用，不表示所有资源已验证。

若需要截图，需取得相应素材并保留 `图片素材/原图/`，放在输出 HTML 的同级目录。截图规则见 [样例说明](examples/kaifeng/README.md)。

### 运行浏览器检查

```bash
python scripts/probe.py --html examples/kaifeng/index.html
```

默认检查宽屏 1440 和窄屏 430：当前探针正常完成时分别执行 30 和 29 项断言，共 59 项，最终 `TOTAL FAIL = 0` 表示检查通过。探针会在页面目录写入临时 `_probe_tmp.html`，运行后尝试删除。

它检查统计、结构、折叠和打开关闭交互；**不证明地点真实存在、截图版权或导航位置准确**。浏览器未启动、瓦片环境或资源问题应结合日志判断。详见 [质量门清单](reference/quality-gates.md)。

## 换成自己的目的地

1. 建立独立工作目录，复制样例 `trip.json`，准备自己的 `data.json`。
2. 改 `meta` 的标题、数据路径和输出名。
3. 改 `geo` 的地图范围、目的地城市、瓦片源与坐标系。国内示例使用 GCJ-02，换数据源时需先核对坐标系。
4. 在 `categoryGroups` 中显式收录每个 `ty`，并配置颜色。
5. 改住处展示名、`labels`、`texts` 和 `notes`，不要保留样例的店名、说明及历史统计。
6. 先运行 `--check-only`，处理错误与告警，再生成页面、运行探针并人工抽查。

`data.json` 是地点数组，最小记录格式如下；这里只展示字段结构，不提供真实坐标：

```json
[
  {
    "id": 1,
    "n": "待核对地点",
    "ty": "小吃",
    "ar": "目标片区"
  }
]
```

无坐标的条目留在清单；若没有 `star:true` 的住处记录，构建会告警，住处距离基准不可用。完整规则见 [数据字段](reference/data-schema.md) 和 [配置字段](reference/config.md)。

## 用 Agent 整理素材

将整个技能目录放入宿主 Agent 支持的技能目录；WorkBuddy 的路径示例是 `~/.workbuddy/skills/trip-map-builder/`。各宿主的安装目录与工具配置不同，其他宿主需自行验证，不能仅凭文件格式判断已兼容。

加载技能后，可以这样提出请求：

> 帮我把这批开封截图整理成自用美食地图。住处照实标注，无法确认的位置保留为未定位。

Agent 按 [SKILL.md](SKILL.md) 识别素材和核验坐标。WorkBuddy 腾讯地图连接器是文档中的首选检索方式；使用前需配置自己的服务权限与 Key。没有连接器时可按 [坐标核验方法](reference/geo-verification.md) 使用其他来源，无法确认的坐标不应编造。Key 不应进入仓库或交付文件。

首次使用可先阅读 [使用指南](GUIDE.md)。

## 质量检查的边界

| 检查 | 当前实现 |
|---|---|
| 数据与配置 | 自动检查必填字段、编号、坐标成对与范围、`loc`、类别覆盖与重复、星标上限、统计和说明位置 |
| 坐标证据 | 技能流程要求在 `rm` 留下检索来源；**构建器不自动验证证据文字或商户真实位置** |
| 来源图片 | `--check-only` 不检查图片；生成时按 `img` 路径检查，部分缺图会中止；全部缺失或资源根目录不存在会告警 |
| 浏览器行为 | 探针检查口径、结构、折叠、交互；实际导航与图片内容另需抽查 |

## 自用地图与公开演示

**默认生成的是用户自用地图**：住处店名、地址与坐标照实标，距离基准才准确。对外分享前再根据用途选择处理方式，见 [SKILL.md 第六节](SKILL.md)。

README 中提到的开封在线案例是**公开演示版**：住处名称泛化、地址到路段、坐标偏移约 500m。随技能分发的 `examples/kaifeng/` 也采用示意住处坐标。因此公开案例和样例中的住处距离仅供演示。

这些处理仅说明公开示例的状态，**不是用户自行生成地图的默认要求**，不要把示意坐标复制成自己的住处坐标。

## 目录与文档导航

```text
trip-map-builder/
├── README.md
├── LICENSE.md
├── SKILL.md                          Agent 工作流程
├── GUIDE.md                          首次使用指南
├── assets/
│   ├── build.py                      数据与配置校验、HTML 构建
│   ├── templates/index.template.html 页面模板
│   └── vendor/leaflet.{js,css}        内联用 Leaflet
├── examples/kaifeng/
│   ├── trip.json                     完整配置样例
│   ├── data.json                     217 条样例记录
│   └── README.md                     资源缺失与示意坐标说明
├── scripts/probe.py                  浏览器回归探针
└── reference/
    ├── config.md                     配置字段
    ├── data-schema.md                数据字段
    ├── geo-verification.md           坐标核验
    └── quality-gates.md              自动检查与人工检查边界
```

## 许可与反馈

原创内容仅供个人学习、研究与非商业使用；商业使用需事先授权，完整条件见 [LICENSE.md](LICENSE.md)。第三方代码、截图和其他外部素材仍遵循各自许可或版权声明。

数据是静态快照，不会自动跟踪商户营业状态。使用问题、文档纠错或授权咨询可通过 [Issues](https://github.com/fang-123559/trip-map-builder/issues) 联系；报告问题时注明 Python、Chrome、系统及复现命令，并去除个人信息和凭据。

文档维护日期：2026-10-12。示例来源的商户信息并非在此日全部重新核验。
