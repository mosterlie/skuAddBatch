"""
SKU 数据文件解析与校验模块
"""
import os
import glob
from typing import List, Dict, Set, Optional, Tuple
from dataclasses import dataclass, field
import sys

# 允许从上级导入 config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


@dataclass(eq=False)
class SkuItem:
    """单个 SKU 变体数据模型"""
    image_name: str         # 对应图片文件名或路径
    image_full_path: str    # 解析后的本地完整绝对路径
    color: str              # 颜色
    size: str               # 尺寸/尺码
    code: str               # 产品编码 / 外部ID
    price: str              # 基本价格
    stock: str              # 库存数量
    condition: str          # 物品状况 (如 "新", "New")
    platform_sku: str       # 平台SKU
    promo_price: str        # 促销价格
    promo_time: str         # 促销时间 (如 "2023-01-01至2023-12-31")
    promo_start: str = ""   # 促销开始日期
    promo_end: str = ""     # 促销结束日期

    def __post_init__(self):
        if "至" in self.promo_time:
            parts = self.promo_time.split("至")
            if len(parts) >= 2:
                self.promo_start = parts[0].strip()
                self.promo_end = parts[1].strip()
        elif "-" in self.promo_time and len(self.promo_time.split("-")) == 6:
            # 格式类似 2023-01-01-2023-12-31
            pass


@dataclass
class SkuDataBundle:
    """完整的数据包模型，包含配置、路径列表与所有 SKU 列表"""
    file_path: str
    base_dir: str
    product_dir: str
    main_image_name: str
    main_image_full_path: str
    detail_dir_name: str
    detail_dir_full_path: str
    detail_image_full_paths: List[str]
    sku_dir_name: str
    sku_dir_full_path: str
    header: List[str]
    items: List[SkuItem] = field(default_factory=list)
    unique_colors: List[str] = field(default_factory=list)
    unique_sizes: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def total_sku_count(self) -> int:
        return len(self.items)

    @property
    def total_product_images(self) -> List[str]:
        """返回所有待上传的产品图片列表 (主图在前，详情图在后)"""
        images = []
        if self.main_image_full_path and os.path.exists(self.main_image_full_path):
            images.append(self.main_image_full_path)
        for d in self.detail_image_full_paths:
            if os.path.exists(d):
                images.append(d)
        return images


class SkuParser:
    """SKU 文本配置文件解析器"""

    @staticmethod
    def _clean_line(line: str) -> str:
        line = line.strip()
        if line.startswith('\ufeff'):  # 处理 UTF-8 BOM
            line = line[1:]
        return line

    @classmethod
    def parse_file(cls, file_path: str) -> SkuDataBundle:
        """读取并解析给定的 SKU txt/csv 数据文件"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"找不到数据文件: {file_path}")

        encodings = ['utf-8', 'utf-8-sig', 'gbk', 'gb18030', 'ansi']
        content = None
        for enc in encodings:
            try:
                with open(file_path, 'r', encoding=enc) as f:
                    content = f.read()
                break
            except (UnicodeDecodeError, Exception):
                continue

        if content is None:
            raise ValueError(f"无法以常见编码 (UTF-8/GBK) 读取文件: {file_path}")

        lines = [cls._clean_line(l) for l in content.splitlines() if cls._clean_line(l) != '']
        if len(lines) < 6:
            raise ValueError("数据文件格式错误：行数少于 6 行配置元数据！")

        # 1. 提取前 5 行路径配置与第 6 行表头
        raw_base_dir = lines[0]
        raw_product_dir = lines[1]
        raw_main_image = lines[2]
        raw_detail_dir = lines[3]
        raw_sku_dir = lines[4]
        raw_header = lines[5]

        # 智能校正 baseDir：如果文件中的 baseDir 在当前系统不存在，尝试使用 txt 文件所在目录的上级或当前目录
        file_dir = os.path.dirname(os.path.abspath(file_path))
        base_dir = raw_base_dir
        if not os.path.exists(base_dir):
            if os.path.exists(os.path.join(file_dir, raw_product_dir)):
                base_dir = file_dir
            elif os.path.exists(os.path.join(os.path.dirname(file_dir), raw_product_dir)):
                base_dir = os.path.dirname(file_dir)

        product_full_dir = os.path.join(base_dir, raw_product_dir)
        main_img_full_path = os.path.join(product_full_dir, raw_main_image)
        detail_full_dir = os.path.join(product_full_dir, raw_detail_dir)
        sku_full_dir = os.path.join(product_full_dir, raw_sku_dir)

        warnings = []
        if not os.path.exists(product_full_dir):
            warnings.append(f"产品目录不存在: {product_full_dir}")

        if not os.path.exists(main_img_full_path):
            warnings.append(f"主图文件不存在: {main_img_full_path}")

        # 扫描详情图
        detail_images = []
        if os.path.exists(detail_full_dir) and os.path.isdir(detail_full_dir):
            for f in os.listdir(detail_full_dir):
                full_p = os.path.join(detail_full_dir, f)
                if os.path.isfile(full_p) and f.lower().endswith(config.IMAGE_EXTENSIONS):
                    detail_images.append(full_p)
            detail_images.sort()
        else:
            warnings.append(f"详情图目录不存在: {detail_full_dir}")

        # 表头拆分
        header_parts = [p.replace('"', '').strip() for p in raw_header.split('"-"')]

        # 2. 解析每行 SKU 数据
        data_lines = lines[6:]
        items: List[SkuItem] = []
        colors_seen: List[str] = []
        sizes_seen: List[str] = []

        for line_idx, line in enumerate(data_lines, start=7):
            clean = line.strip()
            if clean.startswith('"') and clean.endswith('"'):
                clean = clean[1:-1]

            parts = [p.replace('"', '').strip() for p in clean.split('"-"')]
            if len(parts) < 10:
                # 兼容以逗号或 Tab 分隔的场景
                if '\t' in clean:
                    parts = [p.replace('"', '').strip() for p in clean.split('\t')]
                elif ',' in clean:
                    parts = [p.replace('"', '').strip() for p in clean.split(',')]

            if len(parts) >= 10:
                img_name = parts[0]
                color = parts[1]
                size = parts[2]
                code = parts[3]
                price = parts[4]
                stock = parts[5]
                condition = parts[6]
                platform_sku = parts[7]
                promo_price = parts[8]
                promo_time = parts[9]

                # 定位 SKU 图片路径
                # 优先级 1: sku_full_dir / img_name
                # 优先级 2: 直接绝对路径
                # 优先级 3: 模糊搜索 (如匹配 color_size.jpg)
                img_full_path = ""
                if os.path.isabs(img_name) and os.path.exists(img_name):
                    img_full_path = img_name
                else:
                    target_p = os.path.join(sku_full_dir, img_name)
                    if os.path.exists(target_p):
                        img_full_path = target_p
                    else:
                        # 尝试去 product_full_dir 下直接搜索同名文件
                        cand = os.path.join(product_full_dir, img_name)
                        if os.path.exists(cand):
                            img_full_path = cand
                        else:
                            img_full_path = target_p  # 保留目标路径便于日志提示缺失

                if color and color not in colors_seen:
                    colors_seen.append(color)
                if size and size not in sizes_seen:
                    sizes_seen.append(size)

                sku_item = SkuItem(
                    image_name=img_name,
                    image_full_path=img_full_path,
                    color=color,
                    size=size,
                    code=code,
                    price=price,
                    stock=stock,
                    condition=condition,
                    platform_sku=platform_sku,
                    promo_price=promo_price,
                    promo_time=promo_time
                )
                items.append(sku_item)
            else:
                warnings.append(f"第 {line_idx} 行字段不足 10 列，已跳过: {line}")

        bundle = SkuDataBundle(
            file_path=os.path.abspath(file_path),
            base_dir=base_dir,
            product_dir=raw_product_dir,
            main_image_name=raw_main_image,
            main_image_full_path=main_img_full_path,
            detail_dir_name=raw_detail_dir,
            detail_dir_full_path=detail_full_dir,
            detail_image_full_paths=detail_images,
            sku_dir_name=raw_sku_dir,
            sku_dir_full_path=sku_full_dir,
            header=header_parts,
            items=items,
            unique_colors=colors_seen,
            unique_sizes=sizes_seen,
            warnings=warnings
        )
        return bundle


if __name__ == "__main__":
    # 快速自测
    test_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "test_sku.txt"))
    if os.path.exists(test_path):
        print(f"正在测试解析: {test_path}")
        res = SkuParser.parse_file(test_path)
        print(f"解析成功！共 {res.total_sku_count} 个 SKU")
        print(f"颜色 ({len(res.unique_colors)}): {res.unique_colors}")
        print(f"尺码 ({len(res.unique_sizes)}): {res.unique_sizes}")
        print(f"主图路径: {res.main_image_full_path} (存在: {os.path.exists(res.main_image_full_path)})")
        print(f"详情图数量: {len(res.detail_image_full_paths)}")
        print(f"警告列表: {res.warnings}")
