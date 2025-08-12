"""
用户体验验证工具
测试界面响应性、可访问性、移动端适配等用户体验相关功能
"""

import pytest
import time
import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import requests
from typing import Dict, List, Any, Tuple
import os
from pathlib import Path


class UserExperienceValidator:
    """用户体验验证器"""
    
    def __init__(self):
        self.frontend_url = "http://localhost:3000"
        self.backend_url = "http://localhost:8000"
        self.test_results = []
        
        # 设置Chrome选项
        self.chrome_options = Options()
        self.chrome_options.add_argument("--headless")  # 无头模式
        self.chrome_options.add_argument("--no-sandbox")
        self.chrome_options.add_argument("--disable-dev-shm-usage")
        self.chrome_options.add_argument("--disable-gpu")
        self.chrome_options.add_argument("--window-size=1920,1080")
        
        # 移动端测试设备配置
        self.mobile_devices = [
            {"name": "iPhone 12", "width": 390, "height": 844, "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15"},
            {"name": "iPad", "width": 768, "height": 1024, "user_agent": "Mozilla/5.0 (iPad; CPU OS 14_6 like Mac OS X) AppleWebKit/605.1.15"},
            {"name": "Android Phone", "width": 360, "height": 640, "user_agent": "Mozilla/5.0 (Linux; Android 10; SM-G973F) AppleWebKit/537.36"}
        ]
        
        self.driver = None
    
    def run_all_ux_tests(self):
        """运行所有用户体验测试"""
        print("🎨 开始用户体验验证...")
        
        tests = [
            self.test_frontend_accessibility,
            self.test_responsive_design,
            self.test_mobile_compatibility,
            self.test_page_load_performance,
            self.test_interactive_elements,
            self.test_form_usability,
            self.test_error_message_clarity,
            self.test_real_time_updates,
            self.test_keyboard_navigation,
            self.test_visual_feedback,
            self.test_content_readability,
            self.test_workflow_usability
        ]
        
        for test in tests:
            try:
                print(f"\n🔍 运行 {test.__name__}...")
                test()
                print(f"✅ {test.__name__} 完成")
            except Exception as e:
                print(f"❌ {test.__name__} 失败: {e}")
                self.test_results.append({
                    "test": test.__name__,
                    "status": "failed",
                    "error": str(e)
                })
            finally:
                if self.driver:
                    self.driver.quit()
                    self.driver = None
        
        self.generate_ux_report()
    
    def test_frontend_accessibility(self):
        """测试前端可访问性"""
        print("♿ 测试可访问性...")
        
        self.driver = webdriver.Chrome(options=self.chrome_options)
        accessibility_issues = []
        
        try:
            self.driver.get(self.frontend_url)
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # 检查页面标题
            title = self.driver.title
            if not title or len(title.strip()) == 0:
                accessibility_issues.append("页面缺少标题")
            
            # 检查图片的alt属性
            images = self.driver.find_elements(By.TAG_NAME, "img")
            images_without_alt = [img for img in images if not img.get_attribute("alt")]
            if images_without_alt:
                accessibility_issues.append(f"{len(images_without_alt)}个图片缺少alt属性")
            
            # 检查表单标签
            inputs = self.driver.find_elements(By.TAG_NAME, "input")
            unlabeled_inputs = []
            for input_elem in inputs:
                input_type = input_elem.get_attribute("type")
                if input_type not in ["hidden", "submit", "button"]:
                    # 检查是否有关联的label或aria-label
                    has_label = (
                        input_elem.get_attribute("aria-label") or
                        input_elem.get_attribute("aria-labelledby") or
                        self.driver.find_elements(By.CSS_SELECTOR, f"label[for='{input_elem.get_attribute('id')}']")
                    )
                    if not has_label:
                        unlabeled_inputs.append(input_elem)
            
            if unlabeled_inputs:
                accessibility_issues.append(f"{len(unlabeled_inputs)}个输入框缺少标签")
            
            # 检查标题层次结构
            headings = self.driver.find_elements(By.CSS_SELECTOR, "h1, h2, h3, h4, h5, h6")
            heading_levels = [int(h.tag_name[1]) for h in headings]
            
            if heading_levels:
                # 检查是否有h1
                if 1 not in heading_levels:
                    accessibility_issues.append("页面缺少h1标题")
                
                # 检查标题层次是否合理
                for i in range(1, len(heading_levels)):
                    if heading_levels[i] > heading_levels[i-1] + 1:
                        accessibility_issues.append("标题层次结构不合理")
                        break
            
            # 检查颜色对比度（通过检查CSS样式）
            elements_with_low_contrast = self._check_color_contrast()
            if elements_with_low_contrast:
                accessibility_issues.append(f"{len(elements_with_low_contrast)}个元素可能存在对比度问题")
            
            # 检查焦点指示器
            focusable_elements = self.driver.find_elements(By.CSS_SELECTOR, 
                "a, button, input, select, textarea, [tabindex]:not([tabindex='-1'])")
            
            focus_issues = 0
            for element in focusable_elements[:5]:  # 检查前5个可聚焦元素
                try:
                    element.click()
                    # 检查是否有焦点样式
                    outline = element.value_of_css_property("outline")
                    box_shadow = element.value_of_css_property("box-shadow")
                    if outline == "none" and "inset" not in box_shadow:
                        focus_issues += 1
                except:
                    pass
            
            if focus_issues > 2:
                accessibility_issues.append("部分元素缺少焦点指示器")
            
        except Exception as e:
            accessibility_issues.append(f"可访问性测试出错: {str(e)}")
        
        self.test_results.append({
            "test": "frontend_accessibility",
            "status": "passed" if len(accessibility_issues) == 0 else "warning",
            "issues_found": len(accessibility_issues),
            "issues": accessibility_issues,
            "accessibility_score": max(0, 100 - len(accessibility_issues) * 10)
        })
    
    def test_responsive_design(self):
        """测试响应式设计"""
        print("📱 测试响应式设计...")
        
        self.driver = webdriver.Chrome(options=self.chrome_options)
        responsive_results = {}
        
        # 测试不同屏幕尺寸
        screen_sizes = [
            {"name": "Desktop", "width": 1920, "height": 1080},
            {"name": "Laptop", "width": 1366, "height": 768},
            {"name": "Tablet", "width": 768, "height": 1024},
            {"name": "Mobile", "width": 375, "height": 667}
        ]
        
        try:
            for size in screen_sizes:
                print(f"   测试 {size['name']} ({size['width']}x{size['height']})...")
                
                self.driver.set_window_size(size["width"], size["height"])
                self.driver.get(self.frontend_url)
                
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                
                # 检查是否有水平滚动条
                body_width = self.driver.execute_script("return document.body.scrollWidth")
                window_width = self.driver.execute_script("return window.innerWidth")
                has_horizontal_scroll = body_width > window_width
                
                # 检查重要元素是否可见
                important_selectors = [
                    "header", "nav", "main", ".main-content", 
                    "button", ".primary-button", "form"
                ]
                
                visible_elements = 0
                total_elements = 0
                
                for selector in important_selectors:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        total_elements += 1
                        if element.is_displayed():
                            visible_elements += 1
                
                visibility_ratio = visible_elements / total_elements if total_elements > 0 else 1
                
                # 检查文本是否可读（字体大小）
                text_elements = self.driver.find_elements(By.CSS_SELECTOR, "p, span, div, h1, h2, h3, h4, h5, h6")
                small_text_count = 0
                
                for element in text_elements[:10]:  # 检查前10个文本元素
                    try:
                        font_size = element.value_of_css_property("font-size")
                        if font_size and "px" in font_size:
                            size_value = float(font_size.replace("px", ""))
                            if size_value < 14:  # 小于14px认为可能难以阅读
                                small_text_count += 1
                    except:
                        pass
                
                responsive_results[size["name"]] = {
                    "has_horizontal_scroll": has_horizontal_scroll,
                    "element_visibility_ratio": visibility_ratio,
                    "small_text_elements": small_text_count,
                    "layout_score": (
                        (0 if has_horizontal_scroll else 40) +
                        (visibility_ratio * 40) +
                        (20 if small_text_count <= 2 else 0)
                    )
                }
        
        except Exception as e:
            responsive_results["error"] = str(e)
        
        # 计算整体响应式评分
        if "error" not in responsive_results:
            avg_score = sum(result["layout_score"] for result in responsive_results.values()) / len(responsive_results)
            status = "passed" if avg_score >= 80 else "warning" if avg_score >= 60 else "failed"
        else:
            avg_score = 0
            status = "failed"
        
        self.test_results.append({
            "test": "responsive_design",
            "status": status,
            "screen_sizes_tested": len(screen_sizes),
            "results": responsive_results,
            "overall_responsive_score": avg_score
        })
    
    def test_mobile_compatibility(self):
        """测试移动端兼容性"""
        print("📲 测试移动端兼容性...")
        
        mobile_results = {}
        
        for device in self.mobile_devices:
            print(f"   测试 {device['name']}...")
            
            # 设置移动设备仿真
            mobile_emulation = {
                "deviceMetrics": {
                    "width": device["width"],
                    "height": device["height"],
                    "pixelRatio": 2.0
                },
                "userAgent": device["user_agent"]
            }
            
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_experimental_option("mobileEmulation", mobile_emulation)
            
            self.driver = webdriver.Chrome(options=chrome_options)
            
            try:
                self.driver.get(self.frontend_url)
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                
                # 测试触摸友好性
                buttons = self.driver.find_elements(By.TAG_NAME, "button")
                touch_friendly_buttons = 0
                
                for button in buttons[:5]:  # 检查前5个按钮
                    try:
                        size = button.size
                        if size["width"] >= 44 and size["height"] >= 44:  # 44px是推荐的最小触摸目标
                            touch_friendly_buttons += 1
                    except:
                        pass
                
                touch_friendly_ratio = touch_friendly_buttons / min(len(buttons), 5) if buttons else 1
                
                # 测试页面加载速度
                start_time = time.time()
                self.driver.refresh()
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                load_time = time.time() - start_time
                
                # 测试滚动性能
                scroll_smooth = True
                try:
                    self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2)")
                    time.sleep(0.5)
                    self.driver.execute_script("window.scrollTo(0, 0)")
                except:
                    scroll_smooth = False
                
                # 测试表单输入
                inputs = self.driver.find_elements(By.TAG_NAME, "input")
                input_accessibility = 0
                
                for input_elem in inputs[:3]:  # 测试前3个输入框
                    try:
                        input_type = input_elem.get_attribute("type")
                        if input_type in ["text", "email", "password"]:
                            # 检查输入框大小
                            size = input_elem.size
                            if size["height"] >= 40:  # 足够的高度便于点击
                                input_accessibility += 1
                    except:
                        pass
                
                input_accessibility_ratio = input_accessibility / min(len(inputs), 3) if inputs else 1
                
                mobile_results[device["name"]] = {
                    "touch_friendly_ratio": touch_friendly_ratio,
                    "load_time": load_time,
                    "scroll_smooth": scroll_smooth,
                    "input_accessibility_ratio": input_accessibility_ratio,
                    "mobile_score": (
                        touch_friendly_ratio * 30 +
                        (30 if load_time < 3 else 15 if load_time < 5 else 0) +
                        (20 if scroll_smooth else 0) +
                        input_accessibility_ratio * 20
                    )
                }
                
            except Exception as e:
                mobile_results[device["name"]] = {
                    "error": str(e),
                    "mobile_score": 0
                }
            
            finally:
                if self.driver:
                    self.driver.quit()
                    self.driver = None
        
        # 计算整体移动端评分
        scores = [result.get("mobile_score", 0) for result in mobile_results.values()]
        avg_mobile_score = sum(scores) / len(scores) if scores else 0
        
        self.test_results.append({
            "test": "mobile_compatibility",
            "status": "passed" if avg_mobile_score >= 70 else "warning" if avg_mobile_score >= 50 else "failed",
            "devices_tested": len(self.mobile_devices),
            "results": mobile_results,
            "overall_mobile_score": avg_mobile_score
        })
    
    def test_page_load_performance(self):
        """测试页面加载性能"""
        print("⚡ 测试页面加载性能...")
        
        self.driver = webdriver.Chrome(options=self.chrome_options)
        performance_metrics = {}
        
        try:
            # 测试首页加载
            start_time = time.time()
            self.driver.get(self.frontend_url)
            
            # 等待页面完全加载
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # 等待JavaScript加载完成
            WebDriverWait(self.driver, 10).until(
                lambda driver: driver.execute_script("return document.readyState") == "complete"
            )
            
            total_load_time = time.time() - start_time
            
            # 获取浏览器性能指标
            navigation_timing = self.driver.execute_script("""
                var timing = performance.timing;
                return {
                    dns_lookup: timing.domainLookupEnd - timing.domainLookupStart,
                    tcp_connect: timing.connectEnd - timing.connectStart,
                    server_response: timing.responseEnd - timing.requestStart,
                    dom_processing: timing.domComplete - timing.domLoading,
                    page_load: timing.loadEventEnd - timing.navigationStart
                };
            """)
            
            # 测试资源加载
            resources = self.driver.execute_script("""
                return performance.getEntriesByType('resource').map(function(resource) {
                    return {
                        name: resource.name,
                        type: resource.initiatorType,
                        size: resource.transferSize || 0,
                        duration: resource.duration
                    };
                });
            """)
            
            # 分析资源加载情况
            total_resources = len(resources)
            large_resources = [r for r in resources if r.get("size", 0) > 1024 * 1024]  # 大于1MB
            slow_resources = [r for r in resources if r.get("duration", 0) > 3000]  # 加载超过3秒
            
            # 测试图片懒加载
            images = self.driver.find_elements(By.TAG_NAME, "img")
            images_with_lazy_loading = [img for img in images if img.get_attribute("loading") == "lazy"]
            
            performance_metrics = {
                "total_load_time": total_load_time,
                "navigation_timing": navigation_timing,
                "total_resources": total_resources,
                "large_resources_count": len(large_resources),
                "slow_resources_count": len(slow_resources),
                "lazy_loading_ratio": len(images_with_lazy_loading) / len(images) if images else 0,
                "performance_score": self._calculate_performance_score(
                    total_load_time, navigation_timing, len(large_resources), len(slow_resources)
                )
            }
            
        except Exception as e:
            performance_metrics = {"error": str(e), "performance_score": 0}
        
        self.test_results.append({
            "test": "page_load_performance",
            "status": "passed" if performance_metrics.get("performance_score", 0) >= 70 else "warning",
            "metrics": performance_metrics
        })
    
    def test_interactive_elements(self):
        """测试交互元素响应性"""
        print("🖱️ 测试交互元素...")
        
        self.driver = webdriver.Chrome(options=self.chrome_options)
        interaction_results = {}
        
        try:
            self.driver.get(self.frontend_url)
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # 测试按钮点击响应
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            button_responses = []
            
            for i, button in enumerate(buttons[:5]):  # 测试前5个按钮
                try:
                    start_time = time.time()
                    button.click()
                    
                    # 等待可能的视觉反馈或状态变化
                    time.sleep(0.1)
                    
                    response_time = time.time() - start_time
                    button_responses.append(response_time)
                    
                    # 检查是否有视觉反馈
                    has_feedback = self._check_visual_feedback(button)
                    
                except Exception as e:
                    button_responses.append(1.0)  # 默认响应时间
            
            avg_button_response = sum(button_responses) / len(button_responses) if button_responses else 0
            
            # 测试链接
            links = self.driver.find_elements(By.TAG_NAME, "a")
            working_links = 0
            
            for link in links[:5]:  # 测试前5个链接
                try:
                    href = link.get_attribute("href")
                    if href and not href.startswith("javascript:"):
                        # 简单检查链接是否有效（不实际导航）
                        if href.startswith("http") or href.startswith("/"):
                            working_links += 1
                except:
                    pass
            
            link_functionality_ratio = working_links / min(len(links), 5) if links else 1
            
            # 测试表单元素
            form_elements = self.driver.find_elements(By.CSS_SELECTOR, "input, select, textarea")
            responsive_forms = 0
            
            for element in form_elements[:3]:  # 测试前3个表单元素
                try:
                    element_type = element.tag_name
                    if element_type == "input":
                        element.clear()
                        element.send_keys("test")
                        if element.get_attribute("value") == "test":
                            responsive_forms += 1
                    elif element_type in ["select", "textarea"]:
                        responsive_forms += 1
                except:
                    pass
            
            form_responsiveness_ratio = responsive_forms / min(len(form_elements), 3) if form_elements else 1
            
            # 测试拖拽功能（如果存在）
            draggable_elements = self.driver.find_elements(By.CSS_SELECTOR, "[draggable='true']")
            drag_functionality = len(draggable_elements) > 0
            
            interaction_results = {
                "avg_button_response_time": avg_button_response,
                "link_functionality_ratio": link_functionality_ratio,
                "form_responsiveness_ratio": form_responsiveness_ratio,
                "drag_functionality_available": drag_functionality,
                "interaction_score": (
                    (50 if avg_button_response < 0.5 else 25 if avg_button_response < 1.0 else 0) +
                    (link_functionality_ratio * 25) +
                    (form_responsiveness_ratio * 25)
                )
            }
            
        except Exception as e:
            interaction_results = {"error": str(e), "interaction_score": 0}
        
        self.test_results.append({
            "test": "interactive_elements",
            "status": "passed" if interaction_results.get("interaction_score", 0) >= 70 else "warning",
            "results": interaction_results
        })
    
    def test_form_usability(self):
        """测试表单可用性"""
        print("📝 测试表单可用性...")
        
        self.driver = webdriver.Chrome(options=self.chrome_options)
        form_results = {}
        
        try:
            self.driver.get(self.frontend_url)
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # 查找表单
            forms = self.driver.find_elements(By.TAG_NAME, "form")
            
            if forms:
                form = forms[0]  # 测试第一个表单
                
                # 检查表单验证
                inputs = form.find_elements(By.TAG_NAME, "input")
                validation_present = False
                
                for input_elem in inputs:
                    input_type = input_elem.get_attribute("type")
                    required = input_elem.get_attribute("required")
                    pattern = input_elem.get_attribute("pattern")
                    
                    if required is not None or pattern is not None:
                        validation_present = True
                        break
                
                # 测试表单提交
                submit_buttons = form.find_elements(By.CSS_SELECTOR, "button[type='submit'], input[type='submit']")
                submit_functionality = len(submit_buttons) > 0
                
                # 检查错误消息显示
                try:
                    if submit_buttons:
                        # 尝试提交空表单查看验证消息
                        submit_buttons[0].click()
                        time.sleep(1)
                        
                        # 查找错误消息
                        error_messages = self.driver.find_elements(By.CSS_SELECTOR, 
                            ".error, .invalid, [role='alert'], .text-red-500")
                        error_display = len(error_messages) > 0
                    else:
                        error_display = False
                        
                except:
                    error_display = False
                
                # 检查表单字段标签
                labeled_fields = 0
                total_fields = len(inputs)
                
                for input_elem in inputs:
                    input_id = input_elem.get_attribute("id")
                    placeholder = input_elem.get_attribute("placeholder")
                    aria_label = input_elem.get_attribute("aria-label")
                    
                    # 查找关联的label
                    labels = []
                    if input_id:
                        labels = self.driver.find_elements(By.CSS_SELECTOR, f"label[for='{input_id}']")
                    
                    if labels or placeholder or aria_label:
                        labeled_fields += 1
                
                labeling_ratio = labeled_fields / total_fields if total_fields > 0 else 1
                
                form_results = {
                    "forms_found": len(forms),
                    "validation_present": validation_present,
                    "submit_functionality": submit_functionality,
                    "error_display": error_display,
                    "labeling_ratio": labeling_ratio,
                    "usability_score": (
                        (25 if validation_present else 0) +
                        (25 if submit_functionality else 0) +
                        (25 if error_display else 0) +
                        (labeling_ratio * 25)
                    )
                }
                
            else:
                # 没有找到表单，但这不一定是问题
                form_results = {
                    "forms_found": 0,
                    "usability_score": 100,  # 如果没有表单，则认为不适用
                    "note": "未找到表单元素"
                }
            
        except Exception as e:
            form_results = {"error": str(e), "usability_score": 0}
        
        self.test_results.append({
            "test": "form_usability",
            "status": "passed" if form_results.get("usability_score", 0) >= 70 else "warning",
            "results": form_results
        })
    
    def test_error_message_clarity(self):
        """测试错误消息清晰度"""
        print("❗ 测试错误消息清晰度...")
        
        error_scenarios = []
        
        # 测试后端API错误消息
        try:
            # 测试无效请求
            response = requests.post(f"{self.backend_url}/api/v1/tasks/", 
                                   json={"invalid": "data"}, timeout=10)
            
            if response.status_code >= 400:
                try:
                    error_data = response.json()
                    error_message = error_data.get("detail", "") or str(error_data)
                    
                    clarity_score = self._evaluate_error_message_clarity(error_message)
                    error_scenarios.append({
                        "scenario": "invalid_api_request",
                        "status_code": response.status_code,
                        "message": error_message,
                        "clarity_score": clarity_score
                    })
                except:
                    error_scenarios.append({
                        "scenario": "invalid_api_request",
                        "status_code": response.status_code,
                        "message": "无法解析错误消息",
                        "clarity_score": 20
                    })
        except Exception as e:
            error_scenarios.append({
                "scenario": "api_connection_error",
                "message": str(e),
                "clarity_score": 30
            })
        
        # 测试前端错误显示
        self.driver = webdriver.Chrome(options=self.chrome_options)
        
        try:
            self.driver.get(self.frontend_url)
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # 查找错误消息元素
            error_selectors = [
                ".error", ".alert-error", ".text-red-500", ".text-danger",
                "[role='alert']", ".notification-error"
            ]
            
            error_elements_found = 0
            for selector in error_selectors:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                error_elements_found += len(elements)
            
            frontend_error_support = error_elements_found > 0
            
            error_scenarios.append({
                "scenario": "frontend_error_display",
                "error_elements_found": error_elements_found,
                "error_support_available": frontend_error_support,
                "clarity_score": 80 if frontend_error_support else 40
            })
            
        except Exception as e:
            error_scenarios.append({
                "scenario": "frontend_error_check",
                "error": str(e),
                "clarity_score": 0
            })
        
        # 计算整体错误消息质量
        avg_clarity_score = sum(scenario.get("clarity_score", 0) for scenario in error_scenarios) / len(error_scenarios)
        
        self.test_results.append({
            "test": "error_message_clarity",
            "status": "passed" if avg_clarity_score >= 70 else "warning" if avg_clarity_score >= 50 else "failed",
            "scenarios": error_scenarios,
            "overall_clarity_score": avg_clarity_score
        })
    
    def test_real_time_updates(self):
        """测试实时更新功能"""
        print("🔄 测试实时更新...")
        
        self.driver = webdriver.Chrome(options=self.chrome_options)
        realtime_results = {}
        
        try:
            self.driver.get(self.frontend_url)
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # 检查WebSocket连接
            websocket_support = self.driver.execute_script("""
                return typeof WebSocket !== 'undefined';
            """)
            
            # 查找进度条或实时更新元素
            progress_elements = self.driver.find_elements(By.CSS_SELECTOR, 
                ".progress, .progress-bar, [role='progressbar'], .loading")
            
            # 查找实时状态显示
            status_elements = self.driver.find_elements(By.CSS_SELECTOR,
                ".status, .state, .current-status, .agent-status")
            
            # 测试页面是否有自动刷新功能
            initial_timestamp = time.time()
            time.sleep(5)  # 等待5秒观察变化
            
            # 检查页面内容是否有更新
            current_content = self.driver.page_source
            time.sleep(3)
            updated_content = self.driver.page_source
            
            content_updated = current_content != updated_content
            
            realtime_results = {
                "websocket_support": websocket_support,
                "progress_elements_found": len(progress_elements),
                "status_elements_found": len(status_elements),
                "content_auto_update": content_updated,
                "realtime_score": (
                    (30 if websocket_support else 0) +
                    (25 if len(progress_elements) > 0 else 0) +
                    (25 if len(status_elements) > 0 else 0) +
                    (20 if content_updated else 0)
                )
            }
            
        except Exception as e:
            realtime_results = {"error": str(e), "realtime_score": 0}
        
        self.test_results.append({
            "test": "real_time_updates",
            "status": "passed" if realtime_results.get("realtime_score", 0) >= 60 else "warning",
            "results": realtime_results
        })
    
    def test_keyboard_navigation(self):
        """测试键盘导航"""
        print("⌨️ 测试键盘导航...")
        
        self.driver = webdriver.Chrome(options=self.chrome_options)
        keyboard_results = {}
        
        try:
            self.driver.get(self.frontend_url)
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # 获取所有可聚焦元素
            focusable_elements = self.driver.find_elements(By.CSS_SELECTOR,
                "a, button, input, select, textarea, [tabindex]:not([tabindex='-1'])")
            
            # 测试Tab键导航
            tab_navigation_working = True
            focused_elements = []
            
            try:
                # 模拟Tab键导航
                from selenium.webdriver.common.keys import Keys
                body = self.driver.find_element(By.TAG_NAME, "body")
                
                for i in range(min(10, len(focusable_elements))):  # 测试前10个元素
                    body.send_keys(Keys.TAB)
                    time.sleep(0.1)
                    
                    try:
                        active_element = self.driver.switch_to.active_element
                        focused_elements.append(active_element.tag_name)
                    except:
                        tab_navigation_working = False
                        break
                        
            except Exception:
                tab_navigation_working = False
            
            # 检查跳过链接
            skip_links = self.driver.find_elements(By.CSS_SELECTOR, 
                "a[href='#main'], a[href='#content'], .skip-link")
            
            # 检查键盘快捷键支持
            keyboard_shortcuts = self.driver.execute_script("""
                var shortcuts = [];
                var elements = document.querySelectorAll('[data-hotkey], [accesskey]');
                return elements.length;
            """)
            
            keyboard_results = {
                "focusable_elements": len(focusable_elements),
                "tab_navigation_working": tab_navigation_working,
                "focused_elements_count": len(focused_elements),
                "skip_links_available": len(skip_links) > 0,
                "keyboard_shortcuts": keyboard_shortcuts > 0,
                "navigation_score": (
                    (40 if tab_navigation_working else 0) +
                    (20 if len(skip_links) > 0 else 0) +
                    (20 if keyboard_shortcuts > 0 else 0) +
                    (20 if len(focusable_elements) > 0 else 0)
                )
            }
            
        except Exception as e:
            keyboard_results = {"error": str(e), "navigation_score": 0}
        
        self.test_results.append({
            "test": "keyboard_navigation",
            "status": "passed" if keyboard_results.get("navigation_score", 0) >= 60 else "warning",
            "results": keyboard_results
        })
    
    def test_visual_feedback(self):
        """测试视觉反馈"""
        print("👁️ 测试视觉反馈...")
        
        self.driver = webdriver.Chrome(options=self.chrome_options)
        visual_results = {}
        
        try:
            self.driver.get(self.frontend_url)
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # 检查加载指示器
            loading_indicators = self.driver.find_elements(By.CSS_SELECTOR,
                ".loading, .spinner, .loader, [role='status']")
            
            # 检查hover效果
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            hover_effects = 0
            
            for button in buttons[:3]:  # 检查前3个按钮
                try:
                    # 检查是否有hover相关的CSS类或样式
                    classes = button.get_attribute("class") or ""
                    if "hover:" in classes or "transition" in classes:
                        hover_effects += 1
                except:
                    pass
            
            hover_ratio = hover_effects / min(len(buttons), 3) if buttons else 0
            
            # 检查焦点指示器
            focusable = self.driver.find_elements(By.CSS_SELECTOR, "a, button, input")
            focus_indicators = 0
            
            for element in focusable[:3]:
                try:
                    element.click()
                    outline = element.value_of_css_property("outline")
                    box_shadow = element.value_of_css_property("box-shadow")
                    
                    if outline != "none" or "inset" in box_shadow or "0px 0px" in box_shadow:
                        focus_indicators += 1
                except:
                    pass
            
            focus_ratio = focus_indicators / min(len(focusable), 3) if focusable else 0
            
            # 检查动画和过渡效果
            animated_elements = self.driver.find_elements(By.CSS_SELECTOR,
                "[class*='animate'], [class*='transition'], [style*='transition']")
            
            visual_results = {
                "loading_indicators": len(loading_indicators),
                "hover_effects_ratio": hover_ratio,
                "focus_indicators_ratio": focus_ratio,
                "animated_elements": len(animated_elements),
                "visual_feedback_score": (
                    (25 if len(loading_indicators) > 0 else 0) +
                    (hover_ratio * 25) +
                    (focus_ratio * 25) +
                    (25 if len(animated_elements) > 0 else 0)
                )
            }
            
        except Exception as e:
            visual_results = {"error": str(e), "visual_feedback_score": 0}
        
        self.test_results.append({
            "test": "visual_feedback",
            "status": "passed" if visual_results.get("visual_feedback_score", 0) >= 60 else "warning",
            "results": visual_results
        })
    
    def test_content_readability(self):
        """测试内容可读性"""
        print("📖 测试内容可读性...")
        
        self.driver = webdriver.Chrome(options=self.chrome_options)
        readability_results = {}
        
        try:
            self.driver.get(self.frontend_url)
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # 检查字体大小
            text_elements = self.driver.find_elements(By.CSS_SELECTOR, "p, span, div, h1, h2, h3, h4, h5, h6")
            font_sizes = []
            
            for element in text_elements[:20]:  # 检查前20个文本元素
                try:
                    font_size = element.value_of_css_property("font-size")
                    if font_size and "px" in font_size:
                        size_value = float(font_size.replace("px", ""))
                        font_sizes.append(size_value)
                except:
                    pass
            
            avg_font_size = sum(font_sizes) / len(font_sizes) if font_sizes else 16
            readable_font_ratio = sum(1 for size in font_sizes if size >= 14) / len(font_sizes) if font_sizes else 1
            
            # 检查行间距
            line_heights = []
            for element in text_elements[:10]:
                try:
                    line_height = element.value_of_css_property("line-height")
                    if line_height and line_height != "normal":
                        if "px" in line_height:
                            line_heights.append(float(line_height.replace("px", "")))
                        elif line_height.replace(".", "").isdigit():
                            line_heights.append(float(line_height))
                except:
                    pass
            
            avg_line_height = sum(line_heights) / len(line_heights) if line_heights else 1.5
            good_line_spacing = avg_line_height >= 1.4
            
            # 检查颜色对比度
            contrast_issues = self._check_color_contrast()
            good_contrast = len(contrast_issues) < 3
            
            # 检查文本长度（行宽）
            paragraphs = self.driver.find_elements(By.TAG_NAME, "p")
            optimal_line_length = 0
            
            for p in paragraphs[:5]:  # 检查前5个段落
                try:
                    width = p.size["width"]
                    font_size = p.value_of_css_property("font-size")
                    if font_size and "px" in font_size:
                        font_size_px = float(font_size.replace("px", ""))
                        characters_per_line = width / (font_size_px * 0.6)  # 估算
                        if 45 <= characters_per_line <= 75:  # 理想行长
                            optimal_line_length += 1
                except:
                    pass
            
            line_length_ratio = optimal_line_length / min(len(paragraphs), 5) if paragraphs else 1
            
            readability_results = {
                "avg_font_size": avg_font_size,
                "readable_font_ratio": readable_font_ratio,
                "avg_line_height": avg_line_height,
                "good_line_spacing": good_line_spacing,
                "good_contrast": good_contrast,
                "optimal_line_length_ratio": line_length_ratio,
                "readability_score": (
                    (readable_font_ratio * 25) +
                    (25 if good_line_spacing else 0) +
                    (25 if good_contrast else 0) +
                    (line_length_ratio * 25)
                )
            }
            
        except Exception as e:
            readability_results = {"error": str(e), "readability_score": 0}
        
        self.test_results.append({
            "test": "content_readability",
            "status": "passed" if readability_results.get("readability_score", 0) >= 70 else "warning",
            "results": readability_results
        })
    
    def test_workflow_usability(self):
        """测试工作流可用性"""
        print("🔄 测试工作流可用性...")
        
        self.driver = webdriver.Chrome(options=self.chrome_options)
        workflow_results = {}
        
        try:
            self.driver.get(self.frontend_url)
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # 检查导航清晰度
            nav_elements = self.driver.find_elements(By.CSS_SELECTOR, "nav, .navigation, .nav-menu")
            clear_navigation = len(nav_elements) > 0
            
            # 检查面包屑导航
            breadcrumbs = self.driver.find_elements(By.CSS_SELECTOR, 
                ".breadcrumb, .breadcrumbs, [aria-label*='breadcrumb']")
            breadcrumb_available = len(breadcrumbs) > 0
            
            # 检查进度指示器
            progress_indicators = self.driver.find_elements(By.CSS_SELECTOR,
                ".progress, .step, .wizard, [role='progressbar']")
            progress_indication = len(progress_indicators) > 0
            
            # 检查帮助和提示
            help_elements = self.driver.find_elements(By.CSS_SELECTOR,
                ".help, .hint, .tooltip, [title], [aria-describedby]")
            help_available = len(help_elements) > 0
            
            # 检查搜索功能
            search_elements = self.driver.find_elements(By.CSS_SELECTOR,
                "input[type='search'], .search-input, .search-box")
            search_available = len(search_elements) > 0
            
            # 检查撤销/重做功能
            undo_redo = self.driver.find_elements(By.CSS_SELECTOR,
                ".undo, .redo, [title*='undo'], [title*='redo']")
            undo_redo_available = len(undo_redo) > 0
            
            workflow_results = {
                "clear_navigation": clear_navigation,
                "breadcrumb_available": breadcrumb_available,
                "progress_indication": progress_indication,
                "help_available": help_available,
                "search_available": search_available,
                "undo_redo_available": undo_redo_available,
                "workflow_score": (
                    (20 if clear_navigation else 0) +
                    (15 if breadcrumb_available else 0) +
                    (20 if progress_indication else 0) +
                    (15 if help_available else 0) +
                    (15 if search_available else 0) +
                    (15 if undo_redo_available else 0)
                )
            }
            
        except Exception as e:
            workflow_results = {"error": str(e), "workflow_score": 0}
        
        self.test_results.append({
            "test": "workflow_usability",
            "status": "passed" if workflow_results.get("workflow_score", 0) >= 60 else "warning",
            "results": workflow_results
        })
    
    # 辅助方法
    def _check_color_contrast(self) -> List[str]:
        """检查颜色对比度问题"""
        # 这是一个简化的对比度检查
        # 实际应用中可能需要更复杂的颜色分析
        try:
            elements = self.driver.find_elements(By.CSS_SELECTOR, "p, span, a, button, h1, h2, h3, h4, h5, h6")
            contrast_issues = []
            
            for element in elements[:10]:  # 检查前10个元素
                try:
                    color = element.value_of_css_property("color")
                    background = element.value_of_css_property("background-color")
                    
                    # 简单的对比度检查（实际应该使用WCAG算法）
                    if color and background:
                        if color.lower() in ["rgb(128, 128, 128)", "rgba(128, 128, 128, 1)"]:
                            contrast_issues.append(element.tag_name)
                except:
                    pass
            
            return contrast_issues
        except:
            return []
    
    def _check_visual_feedback(self, element) -> bool:
        """检查元素是否有视觉反馈"""
        try:
            # 检查CSS类是否包含反馈相关的样式
            classes = element.get_attribute("class") or ""
            style = element.get_attribute("style") or ""
            
            feedback_indicators = [
                "hover", "active", "focus", "transition", "transform", 
                "shadow", "border", "opacity", "scale"
            ]
            
            return any(indicator in classes.lower() or indicator in style.lower() 
                      for indicator in feedback_indicators)
        except:
            return False
    
    def _calculate_performance_score(self, load_time: float, timing: Dict, large_resources: int, slow_resources: int) -> float:
        """计算性能分数"""
        score = 100
        
        # 加载时间评分
        if load_time > 5:
            score -= 30
        elif load_time > 3:
            score -= 15
        
        # 大资源文件扣分
        score -= large_resources * 10
        
        # 慢资源扣分
        score -= slow_resources * 5
        
        # 服务器响应时间
        server_response = timing.get("server_response", 0)
        if server_response > 1000:  # 大于1秒
            score -= 20
        elif server_response > 500:  # 大于0.5秒
            score -= 10
        
        return max(0, score)
    
    def _evaluate_error_message_clarity(self, message: str) -> float:
        """评估错误消息清晰度"""
        if not message:
            return 0
        
        score = 50  # 基础分
        
        # 长度适中
        if 20 <= len(message) <= 200:
            score += 20
        
        # 包含有用信息
        useful_words = ["required", "invalid", "missing", "error", "failed", "expected"]
        if any(word in message.lower() for word in useful_words):
            score += 15
        
        # 提供解决方案
        solution_words = ["please", "try", "should", "must", "check"]
        if any(word in message.lower() for word in solution_words):
            score += 15
        
        return min(100, score)
    
    def generate_ux_report(self):
        """生成用户体验测试报告"""
        print("\n📊 生成用户体验测试报告...")
        
        passed_tests = sum(1 for result in self.test_results if result["status"] == "passed")
        warning_tests = sum(1 for result in self.test_results if result["status"] == "warning")
        failed_tests = sum(1 for result in self.test_results if result["status"] == "failed")
        total_tests = len(self.test_results)
        
        overall_ux_score = ((passed_tests + warning_tests * 0.7) / total_tests * 100) if total_tests > 0 else 0
        
        print(f"""
        =================== 用户体验测试报告 ===================
        总测试数: {total_tests}
        完全通过: {passed_tests}
        警告状态: {warning_tests}
        完全失败: {failed_tests}
        用户体验评分: {overall_ux_score:.1f}/100
        
        详细结果:
        """)
        
        for result in self.test_results:
            status_icons = {
                "passed": "✅",
                "warning": "⚠️",
                "failed": "❌"
            }
            status_icon = status_icons.get(result["status"], "❓")
            
            print(f"        {status_icon} {result['test']}: {result['status']}")
            
            # 显示关键指标
            if result["test"] == "frontend_accessibility" and "accessibility_score" in result:
                print(f"           可访问性评分: {result['accessibility_score']}/100")
                if result.get("issues_found", 0) > 0:
                    print(f"           发现问题: {result['issues_found']}个")
            
            elif result["test"] == "responsive_design" and "overall_responsive_score" in result:
                print(f"           响应式评分: {result['overall_responsive_score']:.1f}/100")
            
            elif result["test"] == "mobile_compatibility" and "overall_mobile_score" in result:
                print(f"           移动端评分: {result['overall_mobile_score']:.1f}/100")
            
            elif result["test"] == "page_load_performance" and "metrics" in result:
                load_time = result["metrics"].get("total_load_time", 0)
                print(f"           页面加载时间: {load_time:.2f}秒")
            
            if "error" in result:
                print(f"           错误: {result['error']}")
        
        # 用户体验建议
        print(f"""
        
        用户体验改进建议:
        """)
        
        if overall_ux_score >= 90:
            print("        🎉 用户体验优秀！界面设计和交互都很出色")
        elif overall_ux_score >= 80:
            print("        👍 用户体验良好，建议关注可访问性和移动端优化")
        elif overall_ux_score >= 70:
            print("        ⚠️ 用户体验一般，建议改进响应式设计和交互反馈")
        elif overall_ux_score >= 60:
            print("        🔧 用户体验需要改进，重点关注可访问性和性能优化")
        else:
            print("        🚨 用户体验亟需改进，建议全面检查界面设计和交互逻辑")
        
        print("        ===============================================")


# 主测试运行器
def run_user_experience_tests():
    """运行所有用户体验测试"""
    validator = UserExperienceValidator()
    
    try:
        validator.run_all_ux_tests()
        print("🎉 用户体验测试完成！")
        return True
    except Exception as e:
        print(f"❌ 用户体验测试失败: {e}")
        return False


if __name__ == "__main__":
    success = run_user_experience_tests()
    exit(0 if success else 1)