"""
================================================================================
页面内容提取模块 - 提取网页有价值信息
================================================================================

【模块概述】
从网页中提取有价值的内容，如商品信息、价格、评价等。
支持多种电商平台（京东、淘宝、天猫等）。

【核心功能】
1. 识别页面类型（商品列表、商品详情、搜索结果等）
2. 提取商品信息（名称、价格、评价、销量等）
3. 综合多个页面的信息进行总结
================================================================================
"""

import re
import json
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field, asdict
from bs4 import BeautifulSoup, Tag
from playwright.sync_api import Page


@dataclass
class ProductInfo:
    """商品信息数据类"""
    name: str = ""
    price: str = ""
    original_price: str = ""
    review_count: str = ""
    sales_count: str = ""
    shop_name: str = ""
    url: str = ""
    image_url: str = ""
    tags: List[str] = field(default_factory=list)
    description: str = ""
    platform: str = ""
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    def to_summary(self) -> str:
        """生成商品摘要文本"""
        parts = []
        if self.name:
            parts.append(f"商品: {self.name[:50]}")
        if self.price:
            parts.append(f"价格: {self.price}")
        if self.original_price and self.original_price != self.price:
            parts.append(f"原价: {self.original_price}")
        if self.review_count:
            parts.append(f"评价: {self.review_count}")
        if self.sales_count:
            parts.append(f"销量: {self.sales_count}")
        if self.shop_name:
            parts.append(f"店铺: {self.shop_name}")
        return " | ".join(parts)


@dataclass
class PageContent:
    """页面内容数据类"""
    page_type: str = "unknown"
    title: str = ""
    url: str = ""
    products: List[ProductInfo] = field(default_factory=list)
    main_content: str = ""
    key_info: Dict[str, Any] = field(default_factory=dict)
    platform: str = ""
    
    def to_dict(self) -> dict:
        return {
            "page_type": self.page_type,
            "title": self.title,
            "url": self.url,
            "products": [p.to_dict() for p in self.products],
            "main_content": self.main_content,
            "key_info": self.key_info,
            "platform": self.platform
        }


class ContentExtractor:
    """
    页面内容提取器
    
    【设计思路】
    1. 根据URL识别平台和页面类型
    2. 使用平台特定的选择器提取信息
    3. 通用提取方法作为后备
    """
    
    PLATFORM_SELECTORS = {
        "jd": {
            "name": "京东",
            "product_list": {
                "container": ".gl-warp, .goods-list-v2, #J_goodsList, .list-wrap",
                "item": ".gl-item, .goods-item, .gl-i-wrap, li[data-sku]",
                "name": ".p-name a, .p-name.p-name-type-2 a, .goods-name a, .p-name em",
                "price": ".p-price .price, .p-price, i[data-price]",
                "shop": ".p-shop a, .p-shop, .J-hove-wrap a",
                "commit": ".p-commit a, .p-commit, .p-commit strong",
            },
            "product_detail": {
                "name": ".sku-name, .itemInfo-wrap .item-name, .item-name",
                "price": ".price .p-price span, .summary-price-wrap .p-price, .p-price",
                "original_price": ".price .p-del, .summary-price-wrap .p-del",
                "shop": ".shop-name a, .name a, .J-hove-wrap a",
            }
        },
        "taobao": {
            "name": "淘宝",
            "product_list": {
                "container": ".m-itemlist .items, #mainsrp-itemlist .items",
                "item": ".item, .double-items .item",
                "name": ".title a, .row-title a, .J_ClickStat",
                "price": ".price.g_price.g_price-highlight strong, .price strong",
                "shop": ".shop .shopname a, .shopname",
                "sales": ".deal-cnt, .g_price-highlight",
            },
            "product_detail": {
                "name": ".tb-main-title, .ItemHeader--mainTitle",
                "price": ".tb-rmb-num, .Price--priceText",
                "original_price": ".tb-rmb-num del, .Price--originText",
                "shop": ".tb-shop-name a, .ShopHeader--title",
            }
        },
        "tmall": {
            "name": "天猫",
            "product_list": {
                "container": ".m-itemlist .items, #J_ItemList",
                "item": ".item, .product",
                "name": ".productTitle a, .title a",
                "price": ".productPrice em, .price em",
                "shop": ".productShop a, .shop a",
                "sales": ".productStatus em, .deal-cnt",
            },
            "product_detail": {
                "name": ".tb-detail-hd h1, .ItemHeader--mainTitle",
                "price": ".tm-price, .Price--priceText",
                "original_price": ".tm-price del, .Price--originText",
                "shop": ".slogo-shopname, .ShopHeader--title",
            }
        }
    }
    
    PAGE_TYPE_PATTERNS = {
        "product_list": [
            r"search\.", r"list\.", r"category\.", 
            r"/s\?", r"/search", r"/list",
            r"keyword=", r"q=", r"wd="
        ],
        "product_detail": [
            r"item\.", r"detail\.", r"product\.",
            r"/item\?", r"/detail", r"/product/",
            r"id=\d+", r"item_id="
        ],
        "homepage": [
            r"^https?://(www\.)?(jd|taobao|tmall)\.com/?$"
        ]
    }
    
    def __init__(self):
        self.collected_products: List[ProductInfo] = []
        self.collected_content: List[PageContent] = []
    
    def detect_platform(self, url: str) -> str:
        """
        从URL检测平台
        
        【参数】
        url: 页面URL
        
        【返回值】
        str: 平台标识 (jd, taobao, tmall, unknown)
        """
        url_lower = url.lower()
        
        if "jd.com" in url_lower or "jd.hk" in url_lower:
            return "jd"
        elif "tmall.com" in url_lower:
            return "tmall"
        elif "taobao.com" in url_lower:
            return "taobao"
        
        return "unknown"
    
    def detect_page_type(self, url: str, soup: BeautifulSoup) -> str:
        """
        检测页面类型
        
        【参数】
        url: 页面URL
        soup: BeautifulSoup对象
        
        【返回值】
        str: 页面类型 (product_list, product_detail, homepage, unknown)
        """
        url_lower = url.lower()
        
        for page_type, patterns in self.PAGE_TYPE_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, url_lower):
                    return page_type
        
        if soup.select_one(".gl-warp, .goods-list-v2, #J_goodsList"):
            return "product_list"
        if soup.select_one(".m-itemlist .items"):
            return "product_list"
        if soup.select_one(".sku-name, .tb-detail-hd"):
            return "product_detail"
        
        return "unknown"
    
    def extract_price_text(self, element: Tag) -> str:
        """
        从元素中提取价格文本
        
        【参数】
        element: BeautifulSoup元素
        
        【返回值】
        str: 价格文本
        """
        if not element:
            return ""
        
        text = element.get_text(strip=True)
        
        price_match = re.search(r'[\d,]+\.?\d*', text.replace('￥', '').replace('¥', ''))
        if price_match:
            return f"¥{price_match.group()}"
        
        return text[:20] if text else ""
    
    def extract_number(self, text: str) -> str:
        """
        从文本中提取数字
        
        【参数】
        text: 原始文本
        
        【返回值】
        str: 数字文本
        """
        if not text:
            return ""
        
        text = text.strip()
        
        match = re.search(r'[\d,]+\.?\d*[万kK]?', text)
        if match:
            return match.group()
        
        return text[:15] if text else ""
    
    def extract_products_from_list(self, soup: BeautifulSoup, platform: str) -> List[ProductInfo]:
        """
        从商品列表页提取商品信息
        
        【参数】
        soup: BeautifulSoup对象
        platform: 平台标识
        
        【返回值】
        List[ProductInfo]: 商品信息列表
        """
        products = []
        
        selectors = self.PLATFORM_SELECTORS.get(platform, {}).get("product_list", {})
        
        if not selectors:
            return self._extract_products_generic(soup)
        
        items = soup.select(selectors.get("item", ".item"))
        
        if not items:
            items = soup.select(".gl-item, .item, .product, [data-sku], li[class*='item']")
        
        print(f"   🔍 商品提取: 平台={platform}, 找到 {len(items)} 个商品项")
        
        for idx, item in enumerate(items[:20]):
            try:
                product = ProductInfo(platform=platform)
                
                name_elem = item.select_one(selectors.get("name", "a[title]"))
                if name_elem:
                    product.name = name_elem.get("title", "") or name_elem.get_text(strip=True)
                
                price_elem = item.select_one(selectors.get("price", ".price"))
                if price_elem:
                    product.price = self.extract_price_text(price_elem)
                else:
                    price_i = item.select_one("i[data-price]")
                    if price_i:
                        product.price = f"¥{price_i.get('data-price', '')}"
                
                shop_elem = item.select_one(selectors.get("shop", ".shop a"))
                if shop_elem:
                    product.shop_name = shop_elem.get_text(strip=True)
                
                commit_elem = item.select_one(selectors.get("commit", ".commit, .p-commit"))
                if commit_elem:
                    product.review_count = self.extract_number(commit_elem.get_text(strip=True))
                
                sales_elem = item.select_one(selectors.get("sales", ".sales, .deal-cnt"))
                if sales_elem:
                    product.sales_count = self.extract_number(sales_elem.get_text(strip=True))
                
                link_elem = item.select_one("a[href]")
                if link_elem:
                    href = link_elem.get("href", "")
                    if href.startswith("//"):
                        href = "https:" + href
                    product.url = href
                
                img_elem = item.select_one("img[src], img[data-src]")
                if img_elem:
                    product.image_url = img_elem.get("src", "") or img_elem.get("data-src", "")
                
                if product.name or product.price:
                    products.append(product)
                    if idx < 3:
                        print(f"      ✓ 商品{idx+1}: {product.name[:30]}... - {product.price}")
                    
            except Exception as e:
                continue
        
        print(f"   📦 成功提取 {len(products)} 款商品信息")
        return products
    
    def _extract_products_generic(self, soup: BeautifulSoup) -> List[ProductInfo]:
        """
        通用商品提取方法
        
        【参数】
        soup: BeautifulSoup对象
        
        【返回值】
        List[ProductInfo]: 商品信息列表
        """
        products = []
        
        containers = soup.select("[class*='goods'], [class*='product'], [class*='item']")
        
        for container in containers[:20]:
            try:
                product = ProductInfo()
                
                name_elem = container.select_one("a[title], [class*='name'], [class*='title']")
                if name_elem:
                    product.name = name_elem.get("title", "") or name_elem.get_text(strip=True)
                
                price_elem = container.select_one("[class*='price']")
                if price_elem:
                    product.price = self.extract_price_text(price_elem)
                
                if product.name or product.price:
                    products.append(product)
                    
            except Exception:
                continue
        
        return products
    
    def extract_product_detail(self, soup: BeautifulSoup, platform: str) -> ProductInfo:
        """
        从商品详情页提取商品信息
        
        【参数】
        soup: BeautifulSoup对象
        platform: 平台标识
        
        【返回值】
        ProductInfo: 商品信息
        """
        product = ProductInfo(platform=platform)
        
        selectors = self.PLATFORM_SELECTORS.get(platform, {}).get("product_detail", {})
        
        name_elem = soup.select_one(selectors.get("name", "h1, [class*='title']"))
        if name_elem:
            product.name = name_elem.get_text(strip=True)
        
        price_elem = soup.select_one(selectors.get("price", "[class*='price']"))
        if price_elem:
            product.price = self.extract_price_text(price_elem)
        
        original_price_elem = soup.select_one(selectors.get("original_price", "[class*='del']"))
        if original_price_elem:
            product.original_price = self.extract_price_text(original_price_elem)
        
        shop_elem = soup.select_one(selectors.get("shop", "[class*='shop'] a"))
        if shop_elem:
            product.shop_name = shop_elem.get_text(strip=True)
        
        return product
    
    def extract_main_content(self, soup: BeautifulSoup) -> str:
        """
        提取页面主要内容文本
        
        【参数】
        soup: BeautifulSoup对象
        
        【返回值】
        str: 主要内容文本
        """
        for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()
        
        main_selectors = [
            "main", "article", ".main-content", "#content",
            ".product-content", ".detail-content", ".item-detail"
        ]
        
        for selector in main_selectors:
            main = soup.select_one(selector)
            if main:
                text = main.get_text(separator=" ", strip=True)
                if len(text) > 100:
                    return text[:2000]
        
        body = soup.find("body")
        if body:
            text = body.get_text(separator=" ", strip=True)
            return text[:2000]
        
        return ""
    
    def extract_page_content(self, page: Page, url: str = None) -> PageContent:
        """
        从Playwright页面提取内容
        
        【参数】
        page: Playwright页面对象
        url: 页面URL（可选，默认从page获取）
        
        【返回值】
        PageContent: 页面内容
        """
        if url is None:
            url = page.url
        
        try:
            html_content = page.content()
        except Exception as e:
            return PageContent(url=url, main_content=f"获取页面内容失败: {e}")
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        platform = self.detect_platform(url)
        page_type = self.detect_page_type(url, soup)
        
        content = PageContent(
            url=url,
            platform=platform,
            page_type=page_type
        )
        
        title_elem = soup.select_one("title")
        if title_elem:
            content.title = title_elem.get_text(strip=True)
        
        if page_type == "product_list":
            content.products = self.extract_products_from_list(soup, platform)
        elif page_type == "product_detail":
            product = self.extract_product_detail(soup, platform)
            if product.name:
                content.products = [product]
        
        content.main_content = self.extract_main_content(soup)
        
        self.collected_content.append(content)
        self.collected_products.extend(content.products)
        
        return content
    
    def get_products_summary(self, max_products: int = 10) -> str:
        """
        获取已收集商品的摘要
        
        【参数】
        max_products: 最大商品数量
        
        【返回值】
        str: 商品摘要文本
        """
        if not self.collected_products:
            return "暂未收集到商品信息"
        
        unique_products = []
        seen_names = set()
        for p in self.collected_products:
            name_key = p.name[:30] if p.name else ""
            if name_key and name_key not in seen_names:
                seen_names.add(name_key)
                unique_products.append(p)
        
        summaries = []
        for i, product in enumerate(unique_products[:max_products]):
            summaries.append(f"{i+1}. {product.to_summary()}")
        
        return "\n".join(summaries)
    
    def generate_recommendation(self, objective: str, products: List[dict] = None) -> str:
        """
        根据收集的信息生成购买建议
        
        【参数】
        objective: 用户目标
        products: 外部传入的商品列表（可选，优先使用）
        
        【返回值】
        str: 购买建议
        """
        if products:
            use_products = []
            for p in products:
                if isinstance(p, dict):
                    product = ProductInfo(
                        name=p.get("name", ""),
                        price=p.get("price", ""),
                        original_price=p.get("original_price", ""),
                        review_count=p.get("review_count", ""),
                        sales_count=p.get("sales_count", ""),
                        shop_name=p.get("shop_name", ""),
                        platform=p.get("platform", "")
                    )
                    use_products.append(product)
            source_products = use_products
        else:
            source_products = self.collected_products
        
        if not source_products:
            return "未能收集到足够的商品信息，无法提供建议。"
        
        unique_products = []
        seen_names = set()
        for p in source_products:
            name_key = p.name[:30] if p.name else ""
            if name_key and name_key not in seen_names:
                seen_names.add(name_key)
                unique_products.append(p)
        
        if not unique_products:
            return "未能收集到有效的商品信息。"
        
        sorted_by_price = sorted(
            [p for p in unique_products if p.price],
            key=lambda x: self._parse_price(x.price)
        )
        
        recommendation_parts = [
            f"📋 商品搜索结果汇总（共找到 {len(unique_products)} 款商品）",
            ""
        ]
        
        if sorted_by_price:
            cheapest = sorted_by_price[0]
            recommendation_parts.append(f"💰 价格最低: {cheapest.name[:40]} - {cheapest.price}")
            
            if len(sorted_by_price) > 1:
                most_expensive = sorted_by_price[-1]
                recommendation_parts.append(f"💎 价格最高: {most_expensive.name[:40]} - {most_expensive.price}")
        
        sales_products = [p for p in unique_products if p.sales_count]
        if sales_products:
            best_seller = max(sales_products, key=lambda x: self._parse_sales(x.sales_count))
            recommendation_parts.append(f"🔥 销量最高: {best_seller.name[:40]} - 销量: {best_seller.sales_count}")
        
        recommendation_parts.extend([
            "",
            "📊 商品列表:",
            self._format_products_list(unique_products[:10])
        ])
        
        return "\n".join(recommendation_parts)
    
    def _format_products_list(self, products: List[ProductInfo]) -> str:
        """格式化商品列表"""
        lines = []
        for i, p in enumerate(products):
            line = f"  {i+1}. {p.name[:40]}"
            if p.price:
                line += f" | 价格: {p.price}"
            if p.sales_count:
                line += f" | 销量: {p.sales_count}"
            if p.shop_name:
                line += f" | 店铺: {p.shop_name[:15]}"
            lines.append(line)
        return "\n".join(lines)
    
    def _parse_price(self, price_str: str) -> float:
        """解析价格字符串为浮点数"""
        if not price_str:
            return float('inf')
        try:
            cleaned = re.sub(r'[^\d.]', '', price_str)
            return float(cleaned) if cleaned else float('inf')
        except ValueError:
            return float('inf')
    
    def _parse_sales(self, sales_str: str) -> float:
        """解析销量字符串为浮点数"""
        if not sales_str:
            return 0.0
        try:
            sales_str = sales_str.lower()
            if '万' in sales_str:
                match = re.search(r'[\d.]+', sales_str)
                return float(match.group()) * 10000 if match else 0.0
            elif 'k' in sales_str:
                match = re.search(r'[\d.]+', sales_str)
                return float(match.group()) * 1000 if match else 0.0
            else:
                match = re.search(r'[\d.]+', sales_str)
                return float(match.group()) if match else 0.0
        except ValueError:
            return 0.0
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "collected_products": [p.to_dict() for p in self.collected_products],
            "collected_content": [c.to_dict() for c in self.collected_content]
        }
    
    def reset(self):
        """重置收集的内容"""
        self.collected_products.clear()
        self.collected_content.clear()


_content_extractor: Optional[ContentExtractor] = None


def get_content_extractor() -> ContentExtractor:
    """获取全局内容提取器实例"""
    global _content_extractor
    if _content_extractor is None:
        _content_extractor = ContentExtractor()
    return _content_extractor


def extract_content_from_page(page: Page, url: str = None) -> PageContent:
    """
    从页面提取内容的便捷函数
    
    【参数】
    page: Playwright页面对象
    url: 页面URL（可选）
    
    【返回值】
    PageContent: 页面内容
    """
    extractor = get_content_extractor()
    return extractor.extract_page_content(page, url)
