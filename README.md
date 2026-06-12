# PDF Reader

Flask + PyMuPDF 搭建的 PDF 阅读器，支持文字提取、表格检测、代码块渲染、多主题切换。

## 功能

- **PDF 文件浏览** — 目录树懒加载，支持多目录
- **智能文字渲染** — 粗体、斜体、颜色、对齐方式保留
- **表格自动检测与渲染** — 网格分析 → `<table>` 带边框、斑马纹、表头高亮
- **代码块检测** — 等宽字体自动识别，合并行号和截图，去除不可见语法高亮颜色
- **格式保持** — 正文段落连续流式渲染、着重号/编号合并、章节编号合并、页眉页脚淡化
- **图片渲染** — 内嵌图片 base64 输出，空白页占位符
- **乱码检测** — 自动触发图片回退渲染
- **双主题系统** — 界面主题（亮色/暗色）+ 文档主题（正常/复古/反色）
- **阅读进度追踪** — localStorage 持久化，书签续读
- **SFT 缩略图导航** — 小尺寸缩略图网格快速跳转
- **键盘翻页** — ← → 键翻页，支持无限滚动

## 快速开始

```bash
pip install -r requirements.txt
python3 app.py
```

访问 http://localhost:5000

## 配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CONFIG_PATH` | `config.json` | 配置文件路径 |
| `PORT` | `5000` | 服务端口 |

`config.json` 中配置 `pdf_directories` 数组，每项包含 `key`、`path`、`label`。

## 测试

```bash
python3 -m pytest tests/ -v   # 43 tests
```

## 文档

- [架构文档](docs/ARCHITECTURE.md) — API 端点、PDF 处理管线、前端架构、配置说明

## 依赖

- Flask
- PyMuPDF (fitz)
