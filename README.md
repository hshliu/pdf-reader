# PDF Reader

Flask 搭建的 PDF 阅读器，支持文字提取与图片回退渲染。

## 功能

- PDF 文件列表浏览
- 文字提取渲染（支持粗体、斜体、颜色）
- 图片回退渲染（扫描件、乱码页自动降级）
- 多主题切换（经典纸页 / 暗夜护眼 / 新绿清新）
- 阅读进度追踪（本地存储）
- 书签续读
- 键盘翻页（← →）

## 快速开始

```bash
pip install -r requirements.txt

# 设置 PDF 书籍目录
export PDF_DIR=/path/to/pdf/books
python app.py
```

访问 http://localhost:5000

## 配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PDF_DIR` | `/data/apps/sandbox/pdf_books` | PDF 文件存放目录 |
| `PORT` | `5000` | 服务端口 |

## 依赖

- Flask
- PyMuPDF (fitz)
