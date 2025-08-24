"""
Tool Registry - Centralized tool discovery and management system
"""

import asyncio
import inspect
import importlib
from typing import Dict, List, Optional, Type, Any, Set
from pathlib import Path
from dataclasses import dataclass
from threading import Lock
import logging

from .base_tool import BaseTool, ToolMetadata, ToolType, ToolError


@dataclass
class ToolRegistration:
    """Tool registration information"""
    tool_class: Type[BaseTool]
    metadata: ToolMetadata
    config: Dict[str, Any]
    instance: Optional[BaseTool] = None
    is_singleton: bool = True
    auto_load: bool = True


class ToolRegistry:
    """
    Centralized tool registry for discovery, registration, and management
    """
    
    _instance = None
    _lock = Lock()
    
    def __new__(cls):
        """Singleton pattern implementation"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        
        self._tools: Dict[str, ToolRegistration] = {}
        self._tool_instances: Dict[str, BaseTool] = {}
        self._categories: Dict[ToolType, Set[str]] = {}
        self._dependencies: Dict[str, Set[str]] = {}
        self._aliases: Dict[str, str] = {}
        
        self.logger = logging.getLogger("tool_registry")
        self._initialized = True
        self._register_default_ai_tools()  # 🚀 Phase 1.3 - 自动注册AI服务工具
    
    def register_tool(
        self,
        tool_class: Type[BaseTool],
        name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        is_singleton: bool = True,
        auto_load: bool = True,
        aliases: Optional[List[str]] = None
    ) -> str:
        """
        Register a tool class in the registry
        
        Args:
            tool_class: Tool class to register
            name: Tool name (defaults to class metadata)
            config: Tool configuration
            is_singleton: Whether to create singleton instances
            auto_load: Whether to auto-instantiate the tool
            aliases: Alternative names for the tool
        
        Returns:
            Registered tool name
        """
        # Get metadata from tool class
        try:
            # First try class method (for legacy tools)
            if hasattr(tool_class, 'get_metadata') and callable(getattr(tool_class, 'get_metadata')):
                # Check if it's a classmethod by trying to call it directly
                try:
                    metadata = tool_class.get_metadata()
                except TypeError:
                    # If that fails, try instance method
                    temp_instance = tool_class()
                    metadata = temp_instance.get_metadata()
            else:
                # Try to instantiate to get metadata
                temp_instance = tool_class()
                metadata = temp_instance.get_metadata()
        except Exception as e:
            raise ToolError(f"Failed to get metadata for {tool_class.__name__}: {e}")
        
        tool_name = name or metadata.name
        
        # Check for conflicts
        if tool_name in self._tools:
            self.logger.warning(f"Overriding existing tool registration: {tool_name}")
        
        # Create registration
        registration = ToolRegistration(
            tool_class=tool_class,
            metadata=metadata,
            config=config or {},
            is_singleton=is_singleton,
            auto_load=auto_load
        )
        
        self._tools[tool_name] = registration
        
        # Update categories
        if metadata.tool_type not in self._categories:
            self._categories[metadata.tool_type] = set()
        self._categories[metadata.tool_type].add(tool_name)
        
        # Register dependencies
        if metadata.dependencies:
            self._dependencies[tool_name] = set(metadata.dependencies)
        
        # Register aliases
        if aliases:
            for alias in aliases:
                self._aliases[alias] = tool_name
        
        # Auto-instantiate if requested
        if auto_load:
            try:
                self.get_tool(tool_name)
            except Exception as e:
                self.logger.warning(f"Failed to auto-load tool {tool_name}: {e}")
        
        self.logger.info(f"Registered tool: {tool_name} ({metadata.tool_type.value})")
        return tool_name
    
    def unregister_tool(self, name: str):
        """
        Unregister a tool
        
        Args:
            name: Tool name to unregister
        """
        if name not in self._tools:
            raise ToolError(f"Tool not registered: {name}")
        
        registration = self._tools[name]
        
        # Remove from categories
        self._categories[registration.metadata.tool_type].discard(name)
        
        # Remove dependencies
        if name in self._dependencies:
            del self._dependencies[name]
        
        # Remove aliases
        aliases_to_remove = [alias for alias, target in self._aliases.items() if target == name]
        for alias in aliases_to_remove:
            del self._aliases[alias]
        
        # Remove instance
        if name in self._tool_instances:
            del self._tool_instances[name]
        
        # Remove registration
        del self._tools[name]
        
        self.logger.info(f"Unregistered tool: {name}")
    
    def get_tool(self, name: str) -> BaseTool:
        """
        Get tool instance by name
        
        Args:
            name: Tool name or alias
        
        Returns:
            Tool instance
        """
        # Resolve alias
        actual_name = self._aliases.get(name, name)
        
        if actual_name not in self._tools:
            raise ToolError(f"Tool not registered: {name}")
        
        registration = self._tools[actual_name]
        
        # Return singleton instance if available
        if registration.is_singleton and actual_name in self._tool_instances:
            return self._tool_instances[actual_name]
        
        # Create new instance
        try:
            # Check dependencies
            self._check_dependencies(actual_name)
            
            # Create instance
            instance = registration.tool_class(
                metadata=registration.metadata,
                config=registration.config
            )
            
            # Store singleton instance
            if registration.is_singleton:
                self._tool_instances[actual_name] = instance
            
            return instance
            
        except Exception as e:
            raise ToolError(f"Failed to create tool instance {actual_name}: {e}")
    
    def get_tools_by_type(self, tool_type: ToolType) -> List[BaseTool]:
        """
        Get all tools of a specific type
        
        Args:
            tool_type: Tool type to filter by
        
        Returns:
            List of tool instances
        """
        if tool_type not in self._categories:
            return []
        
        tools = []
        for tool_name in self._categories[tool_type]:
            try:
                tools.append(self.get_tool(tool_name))
            except Exception as e:
                self.logger.warning(f"Failed to get tool {tool_name}: {e}")
        
        return tools
    
    def list_tools(self, tool_type: Optional[ToolType] = None) -> List[BaseTool]:
        """
        List registered tools
        
        Args:
            tool_type: Optional tool type filter
        
        Returns:
            List of tool instances
        """
        if tool_type is None:
            tool_names = list(self._tools.keys())
        else:
            tool_names = list(self._categories.get(tool_type, set()))
        
        tools = []
        for tool_name in tool_names:
            try:
                tools.append(self.get_tool(tool_name))
            except Exception as e:
                self.logger.warning(f"Failed to load tool {tool_name}: {e}")
        
        return tools
    
    def get_tool_info(self, name: str) -> Dict[str, Any]:
        """
        Get tool information
        
        Args:
            name: Tool name
        
        Returns:
            Tool information dictionary
        """
        actual_name = self._aliases.get(name, name)
        
        if actual_name not in self._tools:
            raise ToolError(f"Tool not registered: {name}")
        
        registration = self._tools[actual_name]
        
        info = {
            "name": actual_name,
            "class": registration.tool_class.__name__,
            "metadata": {
                "name": registration.metadata.name,
                "version": registration.metadata.version,
                "description": registration.metadata.description,
                "type": registration.metadata.tool_type.value,
                "author": registration.metadata.author,
                "tags": registration.metadata.tags,
                "dependencies": registration.metadata.dependencies,
                "capabilities": registration.metadata.capabilities,
                "limitations": registration.metadata.limitations
            },
            "config": registration.config,
            "is_singleton": registration.is_singleton,
            "auto_load": registration.auto_load,
            "is_loaded": actual_name in self._tool_instances
        }
        
        # Add runtime status if tool is loaded
        if actual_name in self._tool_instances:
            tool_instance = self._tool_instances[actual_name]
            info["status"] = tool_instance.get_status()
        
        return info
    
    def search_tools(
        self,
        query: str = None,
        tool_type: Optional[ToolType] = None,
        tags: Optional[List[str]] = None,
        capabilities: Optional[List[str]] = None
    ) -> List[str]:
        """
        Search for tools based on criteria
        
        Args:
            query: Text search query
            tool_type: Tool type filter
            tags: Required tags
            capabilities: Required capabilities
        
        Returns:
            List of matching tool names
        """
        matching_tools = []
        
        for tool_name, registration in self._tools.items():
            metadata = registration.metadata
            
            # Type filter
            if tool_type and metadata.tool_type != tool_type:
                continue
            
            # Text search
            if query:
                searchable_text = f"{metadata.name} {metadata.description} {' '.join(metadata.tags)}".lower()
                if query.lower() not in searchable_text:
                    continue
            
            # Tags filter
            if tags:
                if not all(tag in metadata.tags for tag in tags):
                    continue
            
            # Capabilities filter
            if capabilities:
                if not all(cap in metadata.capabilities for cap in capabilities):
                    continue
            
            matching_tools.append(tool_name)
        
        return matching_tools
    
    def _check_dependencies(self, tool_name: str):
        """Check if tool dependencies are satisfied"""
        if tool_name not in self._dependencies:
            return
        
        for dependency in self._dependencies[tool_name]:
            if dependency not in self._tools:
                raise ToolError(f"Missing dependency for {tool_name}: {dependency}")
    
    def get_dependency_graph(self) -> Dict[str, List[str]]:
        """Get tool dependency graph"""
        return {name: list(deps) for name, deps in self._dependencies.items()}
    
    def validate_registry(self) -> List[str]:
        """
        Validate the registry and return list of issues
        
        Returns:
            List of validation issues
        """
        issues = []
        
        # Check dependencies
        for tool_name, dependencies in self._dependencies.items():
            for dependency in dependencies:
                if dependency not in self._tools:
                    issues.append(f"Tool {tool_name} has missing dependency: {dependency}")
        
        # Check for circular dependencies
        def has_circular_dependency(tool_name: str, visited: Set[str]) -> bool:
            if tool_name in visited:
                return True
            
            visited.add(tool_name)
            
            for dependency in self._dependencies.get(tool_name, []):
                if has_circular_dependency(dependency, visited.copy()):
                    return True
            
            return False
        
        for tool_name in self._tools:
            if has_circular_dependency(tool_name, set()):
                issues.append(f"Circular dependency detected for tool: {tool_name}")
        
        return issues
    
    def auto_discover_tools(self, package_path: str = "agents.tools"):
        """
        Automatically discover and register tools from a package
        
        Args:
            package_path: Python package path to search
        """
        try:
            package = importlib.import_module(package_path)
            package_dir = Path(package.__file__).parent
            
            # Find all Python files
            for py_file in package_dir.rglob("*.py"):
                if py_file.name.startswith("__"):
                    continue
                
                # Convert file path to module path
                relative_path = py_file.relative_to(package_dir.parent)
                module_path = str(relative_path.with_suffix("")).replace("/", ".")
                
                try:
                    module = importlib.import_module(module_path)
                    
                    # Find tool classes
                    for name, obj in inspect.getmembers(module, inspect.isclass):
                        if (issubclass(obj, BaseTool) and 
                            obj != BaseTool and 
                            not inspect.isabstract(obj)):
                            
                            try:
                                self.register_tool(obj)
                            except Exception as e:
                                self.logger.warning(f"Failed to register tool {name}: {e}")
                
                except ImportError as e:
                    self.logger.debug(f"Skipping module {module_path}: {e}")
                
        except Exception as e:
            self.logger.error(f"Auto-discovery failed: {e}")
    
    def reload_tool(self, name: str):
        """
        Reload a tool (useful for development)
        
        Args:
            name: Tool name to reload
        """
        if name not in self._tools:
            raise ToolError(f"Tool not registered: {name}")
        
        registration = self._tools[name]
        
        # Remove existing instance
        if name in self._tool_instances:
            del self._tool_instances[name]
        
        # Reload module
        module = inspect.getmodule(registration.tool_class)
        if module:
            importlib.reload(module)
        
        # Re-instantiate if auto-load is enabled
        if registration.auto_load:
            try:
                self.get_tool(name)
            except Exception as e:
                self.logger.warning(f"Failed to reload tool {name}: {e}")
        
        self.logger.info(f"Reloaded tool: {name}")
    
    def get_registry_stats(self) -> Dict[str, Any]:
        """Get registry statistics"""
        return {
            "total_tools": len(self._tools),
            "loaded_tools": len(self._tool_instances),
            "tools_by_type": {
                tool_type.value: len(tools) 
                for tool_type, tools in self._categories.items()
            },
            "total_aliases": len(self._aliases),
            "tools_with_dependencies": len(self._dependencies),
            "validation_issues": len(self.validate_registry())
        }
    
    def _register_default_ai_tools(self):
        """🚀 Phase 1.3 - 自动注册原子性AI服务工具"""
        try:
            # 注册概念生成工具
            from .ai_services.concept_generation_tool import ConceptGenerationTool
            self.register_tool(
                tool_class=ConceptGenerationTool,
                name="concept_generation_tool",
                config={},
                is_singleton=True,
                auto_load=False
            )
            
            # 注册场景脚本生成工具
            from .ai_services.scene_script_generation_tool import SceneScriptGenerationTool
            self.register_tool(
                tool_class=SceneScriptGenerationTool,
                name="scene_script_generation_tool",
                config={},
                is_singleton=True,
                auto_load=False
            )
            
            # 注册叙事结构生成工具
            from .ai_services.narrative_structure_generation_tool import NarrativeStructureGenerationTool
            self.register_tool(
                tool_class=NarrativeStructureGenerationTool,
                name="narrative_structure_generation_tool",
                config={},
                is_singleton=True,
                auto_load=False
            )
            
            # 注册质量分析工具
            from .ai_services.quality_analysis_tool import QualityAnalysisTool
            self.register_tool(
                tool_class=QualityAnalysisTool,
                name="quality_analysis_tool",
                config={},
                is_singleton=True,
                auto_load=False
            )
            
            # 注册场景连续性分析工具
            from .ai_services.scene_continuity_analysis_tool import SceneContinuityAnalysisTool
            self.register_tool(
                tool_class=SceneContinuityAnalysisTool,
                name="scene_continuity_analysis_tool",
                config={},
                is_singleton=True,
                auto_load=False
            )
            
            self.logger.info("🤖 原子性AI服务工具注册完成")
            
        except Exception as e:
            self.logger.warning(f"⚠️ 原子性AI工具注册失败: {e}")
            # 不抛出异常，避免影响整个注册系统的初始化


# Global registry instance
tool_registry = ToolRegistry()


def get_tool_registry() -> ToolRegistry:
    """Get global tool registry instance"""
    return tool_registry