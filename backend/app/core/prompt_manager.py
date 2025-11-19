"""
统一提示词管理系统 - 支持YAML配置和Jinja2模板渲染
"""

import os
import yaml
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, Template, TemplateNotFound
from threading import Lock
import hashlib


class PromptTemplate:
    """提示词模板类"""
    
    def __init__(self, name: str, template: str, variables: List[str] = None, description: str = ""):
        self.name = name
        self.template = template
        self.variables = variables or []
        self.description = description
        self._compiled_template = None
    
    @property
    def compiled_template(self) -> Template:
        """获取编译后的Jinja2模板"""
        if self._compiled_template is None:
            env = Environment()
            self._compiled_template = env.from_string(self.template)
        return self._compiled_template
    
    def render(self, **kwargs) -> str:
        """渲染模板"""
        # 检查必需变量
        missing_vars = [var for var in self.variables if var not in kwargs]
        if missing_vars:
            raise ValueError(f"Missing required variables: {missing_vars}")
        
        return self.compiled_template.render(**kwargs)
    
    def get_cache_key(self, **kwargs) -> str:
        """生成缓存键"""
        content = f"{self.name}:{str(sorted(kwargs.items()))}"
        return hashlib.md5(content.encode()).hexdigest()


class PromptConfig:
    """提示词配置类"""
    
    def __init__(self, config_data: Dict[str, Any]):
        self.name = config_data.get("name", "")
        self.description = config_data.get("description", "")
        self.version = config_data.get("version", "1.0.0")
        # 记录该配置来源文件路径（便于诊断）
        self.source_path: str = ""
        
        # 角色设定
        self.role = config_data.get("role", {})
        
        # 系统指令
        self.system_instructions = config_data.get("system_instructions", {})
        
        # 模板集合
        self.templates = {}
        templates_data = config_data.get("templates", {})
        for template_name, template_data in templates_data.items():
            # 支持新的required_variables/optional_variables格式
            variables = template_data.get("variables", [])
            if not variables:
                # 新格式：优先使用required_variables
                variables = template_data.get("required_variables", [])
            
            # 获取模板内容
            template_content = template_data.get("template", "")
            
            # 支持外部Jinja2文件
            if template_data.get("type") == "jinja2_file" and template_data.get("template_file"):
                # Template files are in app/agents/prompts/templates/
                template_file_path = Path(__file__).parent.parent / "agents" / "prompts" / "templates" / template_data["template_file"]
                if template_file_path.exists():
                    try:
                        with open(template_file_path, 'r', encoding='utf-8') as f:
                            template_content = f.read()
                    except Exception as e:
                        self.logger.warning(f"Failed to load template file {template_file_path}: {e}")
                else:
                    self.logger.warning(f"Template file not found: {template_file_path}")
            
            self.templates[template_name] = PromptTemplate(
                name=template_name,
                template=template_content,
                variables=variables,
                description=template_data.get("description", "")
            )
        
        # 元数据
        self.metadata = config_data.get("metadata", {})


class PromptManager:
    """
    统一提示词管理器
    
    功能：
    1. 加载和管理YAML格式的提示词配置
    2. 支持Jinja2模板渲染
    3. 提供缓存机制提高性能
    4. 支持热重载（开发模式）
    """
    
    def __init__(self, config_path: str = None):
        """
        初始化提示词管理器
        
        Args:
            config_path: 配置文件根目录路径
        """
        if config_path is None:
            # 默认配置路径优先使用 app/config/prompts，其次兼容 legacy backend/config/prompts
            app_root = Path(__file__).parent.parent  # backend/app
            app_cfg = app_root / "config" / "prompts"
            legacy_cfg = app_root.parent / "config" / "prompts"  # backend/config/prompts
            if app_cfg.exists():
                config_path = app_cfg
            else:
                config_path = legacy_cfg
        
        self.config_path = Path(config_path)
        self.logger = logging.getLogger("prompt_manager")
        
        # 确保配置目录存在
        self.config_path.mkdir(parents=True, exist_ok=True)
        
        # 配置缓存
        self._configs: Dict[str, PromptConfig] = {}
        self._file_mtimes: Dict[str, float] = {}
        self._render_cache: Dict[str, str] = {}
        
        # 线程锁
        self._lock = Lock()
        
        # 加载所有配置
        self._load_all_configs()
    
    def _load_all_configs(self):
        """加载所有配置文件"""
        try:
            # 首选当前 config_path
            for sub in ("agents", "templates"):
                p = self.config_path / sub
                if p.exists():
                    for yaml_file in p.glob("*.yaml"):
                        self._load_config_file(yaml_file)
            # 兼容加载 legacy 目录（避免遗漏），但不覆盖已有同名配置
            legacy_root = (Path(__file__).parent.parent.parent / "config" / "prompts")
            if legacy_root.resolve() != self.config_path.resolve():
                for sub in ("agents", "templates"):
                    p = legacy_root / sub
                    if p.exists():
                        for yaml_file in p.glob("*.yaml"):
                            name = yaml_file.stem
                            if name not in self._configs:
                                self._load_config_file(yaml_file)
            self.logger.info(f"Loaded {len(self._configs)} prompt configurations from {self.config_path}")

        except Exception as e:
            self.logger.error(f"Failed to load prompt configurations: {e}")
            raise
    
    def _load_config_file(self, config_file: Path):
        """加载单个配置文件"""
        try:
            config_name = config_file.stem
            
            with open(config_file, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
            
            config = PromptConfig(config_data)
            try:
                config.source_path = str(config_file)
            except Exception:
                config.source_path = str(config_file)
            
            with self._lock:
                self._configs[config_name] = config
                self._file_mtimes[str(config_file)] = config_file.stat().st_mtime
            
            self.logger.debug(f"Loaded config: {config_name} from {config_file}")
            
        except Exception as e:
            self.logger.error(f"Failed to load config file {config_file}: {e}")
            raise
    
    def _check_file_changed(self, config_name: str) -> bool:
        """检查配置文件是否已更改"""
        config_file = self.config_path / "agents" / f"{config_name}.yaml"
        if not config_file.exists():
            config_file = self.config_path / "templates" / f"{config_name}.yaml"
        
        if not config_file.exists():
            return False
            
        current_mtime = config_file.stat().st_mtime
        cached_mtime = self._file_mtimes.get(str(config_file), 0)
        
        return current_mtime > cached_mtime
    
    def get_config(self, config_name: str, auto_reload: bool = False) -> Optional[PromptConfig]:
        """
        获取提示词配置
        
        Args:
            config_name: 配置名称
            auto_reload: 是否自动重载（开发模式）
            
        Returns:
            PromptConfig对象或None
        """
        # 兼容：允许传入带路径的名称（如 "agents/image_generator"），仅取文件名部分作为配置名
        try:
            import os
            if isinstance(config_name, str) and ("/" in config_name or "\\" in config_name):
                config_name = os.path.basename(config_name)
        except Exception:
            pass
        # 自动重载检查
        if auto_reload and self._check_file_changed(config_name):
            self.reload_config(config_name)
        
        return self._configs.get(config_name)
    
    def get_template(self, config_name: str, template_name: str, auto_reload: bool = False) -> Optional[PromptTemplate]:
        """
        获取特定模板
        
        Args:
            config_name: 配置名称
            template_name: 模板名称
            auto_reload: 是否自动重载
            
        Returns:
            PromptTemplate对象或None
        """
        config = self.get_config(config_name, auto_reload)
        if not config:
            return None
        
        return config.templates.get(template_name)
    
    def render_template(
        self, 
        config_name: str, 
        template_name: str, 
        variables: Dict[str, Any], 
        use_cache: bool = True,
        auto_reload: bool = False
    ) -> str:
        """
        渲染模板
        
        Args:
            config_name: 配置名称
            template_name: 模板名称  
            variables: 模板变量
            use_cache: 是否使用缓存
            auto_reload: 是否自动重载
            
        Returns:
            渲染后的文本
            
        Raises:
            ValueError: 模板不存在或变量缺失
        """
        template = self.get_template(config_name, template_name, auto_reload)
        if not template:
            raise ValueError(f"Template not found: {config_name}.{template_name}")
        
        # 检查缓存（修正：加入 config_name 以避免不同配置的同名模板互相污染）
        if use_cache:
            try:
                cache_key = f"{config_name}:{template.name}:{template.get_cache_key(**variables)}"
            except Exception:
                cache_key = template.get_cache_key(**variables)
            cached_result = self._render_cache.get(cache_key)
            if cached_result:
                return cached_result
        
        # 渲染模板
        try:
            result = template.render(**variables)
            
            # 存入缓存
            if use_cache:
                with self._lock:
                    # 与读取时采用同样的 cache_key 规则
                    try:
                        final_cache_key = f"{config_name}:{template.name}:{template.get_cache_key(**variables)}"
                    except Exception:
                        final_cache_key = template.get_cache_key(**variables)
                    self._render_cache[final_cache_key] = result
            
            return result
            
        except Exception as e:
            self.logger.error(f"Failed to render template {config_name}.{template_name}: {e}")
            raise
    
    def reload_config(self, config_name: str):
        """重新加载配置"""
        config_file = self.config_path / "agents" / f"{config_name}.yaml"
        if not config_file.exists():
            config_file = self.config_path / "templates" / f"{config_name}.yaml"
        
        if config_file.exists():
            self._load_config_file(config_file)
            # 清除相关缓存
            self._clear_cache(config_name)
            self.logger.info(f"Reloaded config: {config_name}")
        else:
            self.logger.warning(f"Config file not found for reload: {config_name}")
    
    def _clear_cache(self, config_name: str):
        """清除指定配置的缓存"""
        with self._lock:
            # 清除渲染缓存（简单粗暴，清除所有）
            self._render_cache.clear()
    
    def list_configs(self) -> List[str]:
        """获取所有配置名称"""
        return list(self._configs.keys())
    
    def list_templates(self, config_name: str) -> List[str]:
        """获取指定配置的所有模板名称"""
        config = self.get_config(config_name)
        if not config:
            return []
        return list(config.templates.keys())
    
    def get_system_instruction(self, config_name: str) -> Dict[str, Any]:
        """获取系统指令"""
        config = self.get_config(config_name)
        if not config:
            return {}
        return config.system_instructions
    
    def get_role_info(self, config_name: str) -> Dict[str, Any]:
        """获取角色信息"""
        config = self.get_config(config_name)
        if not config:
            return {}
        return config.role
    
    def clear_all_cache(self):
        """清除所有缓存"""
        with self._lock:
            self._render_cache.clear()
        self.logger.info("Cleared all prompt cache")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取管理器统计信息"""
        return {
            "total_configs": len(self._configs),
            "cache_size": len(self._render_cache),
            "config_names": list(self._configs.keys())
        }


# 全局单例实例
_prompt_manager = None
_manager_lock = Lock()


def get_prompt_manager(config_path: str = None) -> PromptManager:
    """获取全局提示词管理器实例（单例模式）"""
    global _prompt_manager
    
    if _prompt_manager is None:
        with _manager_lock:
            if _prompt_manager is None:
                _prompt_manager = PromptManager(config_path)
    
    return _prompt_manager


# 便捷函数
def render_prompt(config_name: str, template_name: str, **variables) -> str:
    """便捷的提示词渲染函数"""
    manager = get_prompt_manager()
    return manager.render_template(config_name, template_name, variables)


def get_system_prompt(config_name: str) -> Dict[str, Any]:
    """获取系统提示词"""
    manager = get_prompt_manager()
    return manager.get_system_instruction(config_name)
