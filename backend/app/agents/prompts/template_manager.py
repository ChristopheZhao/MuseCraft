"""
Prompt Template Manager - Centralized management for LLM prompt templates
"""

import json
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass, asdict
from datetime import datetime
import logging
from jinja2 import Environment, FileSystemLoader, Template, TemplateNotFound


@dataclass
class PromptMetadata:
    """Metadata for prompt templates"""
    name: str
    version: str
    description: str
    author: str
    created_at: datetime
    updated_at: datetime
    tags: List[str]
    variables: List[str]
    model_requirements: Dict[str, Any]
    usage_examples: List[str]


class PromptTemplate:
    """Prompt template with metadata and rendering capabilities"""
    
    def __init__(
        self,
        name: str,
        template_content: str,
        metadata: PromptMetadata,
        template_type: str = "jinja2"
    ):
        self.name = name
        self.template_content = template_content
        self.metadata = metadata
        self.template_type = template_type
        
        # Create Jinja2 template
        if template_type == "jinja2":
            self.template = Environment().from_string(template_content)
        else:
            self.template = None
    
    def render(self, variables: Dict[str, Any]) -> str:
        """Render template with provided variables"""
        if self.template_type == "jinja2" and self.template:
            return self.template.render(**variables)
        else:
            # Simple string formatting fallback
            return self.template_content.format(**variables)
    
    def validate_variables(self, variables: Dict[str, Any]) -> List[str]:
        """Validate that all required variables are provided"""
        missing_vars = []
        for required_var in self.metadata.variables:
            if required_var not in variables:
                missing_vars.append(required_var)
        return missing_vars
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation"""
        return {
            "name": self.name,
            "template_content": self.template_content,
            "metadata": asdict(self.metadata),
            "template_type": self.template_type
        }


class TemplateValidationError(Exception):
    """Raised when template validation fails"""
    pass


class TemplateNotFoundError(Exception):
    """Raised when template is not found"""
    pass


class PromptTemplateManager:
    """
    Centralized manager for prompt templates
    
    Provides template loading, caching, rendering, and management
    """
    
    def __init__(self, template_directories: List[str] = None, agent_name: str = None):
        self.template_directories = template_directories or []
        self.templates: Dict[str, PromptTemplate] = {}
        self.logger = logging.getLogger("prompt_template_manager")
        self.agent_name = agent_name
        
        # Set up template directories based on agent_name
        base_template_dir = Path(__file__).parent / "templates"
        
        if agent_name:
            # Agent-specific loading: agent directory + common directory
            agent_dir = str(base_template_dir / agent_name)
            common_dir = str(base_template_dir / "common")
            
            # Add agent-specific directory
            if agent_dir not in self.template_directories:
                self.template_directories.append(agent_dir)
            
            # Add common directory for shared templates
            if common_dir not in self.template_directories:
                self.template_directories.append(common_dir)
                
            self.logger.info(f"Loading templates for agent '{agent_name}' from: {self.template_directories}")
        else:
            # Load all templates (backward compatibility)
            default_dir = str(base_template_dir)
            if default_dir not in self.template_directories:
                self.template_directories.append(default_dir)
        
        # Create Jinja2 environment
        self.jinja_env = Environment(
            loader=FileSystemLoader(self.template_directories),
            trim_blocks=True,
            lstrip_blocks=True
        )
        
        # Template cache
        self._template_cache = {}
        self._metadata_cache = {}
        
        # Load templates on initialization
        self._load_all_templates()
    
    def _load_all_templates(self):
        """Load all templates from template directories"""
        for template_dir in self.template_directories:
            template_path = Path(template_dir)
            if not template_path.exists():
                self.logger.warning(f"Template directory does not exist: {template_dir}")
                continue
            
            # Look for template files
            for template_file in template_path.glob("**/*.yaml"):
                try:
                    self._load_template_from_file(template_file)
                except Exception as e:
                    self.logger.error(f"Failed to load template from {template_file}: {e}")
            
            for template_file in template_path.glob("**/*.yml"):
                try:
                    self._load_template_from_file(template_file)
                except Exception as e:
                    self.logger.error(f"Failed to load template from {template_file}: {e}")
            
            # Load jinja2 template files
            for template_file in template_path.glob("**/*.jinja2"):
                try:
                    self._load_jinja2_template_from_file(template_file)
                except Exception as e:
                    self.logger.error(f"Failed to load jinja2 template from {template_file}: {e}")
    
    def _load_template_from_file(self, template_file: Path):
        """Load template from YAML file"""
        with open(template_file, 'r', encoding='utf-8') as f:
            template_data = yaml.safe_load(f)
        
        # Extract metadata
        metadata_dict = template_data.get("metadata", {})
        metadata = PromptMetadata(
            name=metadata_dict.get("name", template_file.stem),
            version=metadata_dict.get("version", "1.0.0"),
            description=metadata_dict.get("description", ""),
            author=metadata_dict.get("author", "unknown"),
            created_at=datetime.fromisoformat(metadata_dict.get("created_at", datetime.now().isoformat())),
            updated_at=datetime.fromisoformat(metadata_dict.get("updated_at", datetime.now().isoformat())),
            tags=metadata_dict.get("tags", []),
            variables=metadata_dict.get("variables", []),
            model_requirements=metadata_dict.get("model_requirements", {}),
            usage_examples=metadata_dict.get("usage_examples", [])
        )
        
        # Create template
        template_content = template_data.get("template", "")
        template_type = template_data.get("type", "jinja2")
        
        template = PromptTemplate(
            name=metadata.name,
            template_content=template_content,
            metadata=metadata,
            template_type=template_type
        )
        
        self.templates[metadata.name] = template
        self.logger.info(f"Loaded template: {metadata.name}")
    
    def _load_jinja2_template_from_file(self, template_file: Path):
        """Load jinja2 template directly from .jinja2 file"""
        with open(template_file, 'r', encoding='utf-8') as f:
            template_content = f.read()
        
        # Create minimal metadata for jinja2 files
        template_name = template_file.stem
        metadata = PromptMetadata(
            name=template_name,
            version="1.0.0",
            description=f"Jinja2 template loaded from {template_file.name}",
            author="system",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            tags=["jinja2"],
            variables=[],  # Could be extracted from template content if needed
            model_requirements={},
            usage_examples=[]
        )
        
        # Create template
        template = PromptTemplate(
            name=template_name,
            template_content=template_content,
            metadata=metadata,
            template_type="jinja2"
        )
        
        self.templates[template_name] = template
        self.logger.info(f"Loaded jinja2 template: {template_name}")
    
    def get_template(self, name: str) -> PromptTemplate:
        """Get template by name"""
        if name not in self.templates:
            raise TemplateNotFoundError(f"Template not found: {name}")
        return self.templates[name]
    
    def list_templates(self, tags: List[str] = None) -> List[str]:
        """List available templates, optionally filtered by tags"""
        template_names = []
        
        for name, template in self.templates.items():
            if tags:
                if any(tag in template.metadata.tags for tag in tags):
                    template_names.append(name)
            else:
                template_names.append(name)
        
        return sorted(template_names)
    
    def render_template(
        self, 
        name: str, 
        variables: Dict[str, Any],
        validate: bool = True
    ) -> str:
        """Render template with provided variables"""
        template = self.get_template(name)
        
        if validate:
            missing_vars = template.validate_variables(variables)
            if missing_vars:
                raise TemplateValidationError(
                    f"Missing required variables for template '{name}': {missing_vars}"
                )
        
        try:
            return template.render(variables)
        except Exception as e:
            raise TemplateValidationError(f"Failed to render template '{name}': {str(e)}")
    
    def create_template(
        self,
        name: str,
        template_content: str,
        metadata: Dict[str, Any],
        template_type: str = "jinja2",
        save_to_disk: bool = True
    ) -> PromptTemplate:
        """Create new template"""
        # Create metadata object
        template_metadata = PromptMetadata(
            name=name,
            version=metadata.get("version", "1.0.0"),
            description=metadata.get("description", ""),
            author=metadata.get("author", "system"),
            created_at=datetime.now(),
            updated_at=datetime.now(),
            tags=metadata.get("tags", []),
            variables=metadata.get("variables", []),
            model_requirements=metadata.get("model_requirements", {}),
            usage_examples=metadata.get("usage_examples", [])
        )
        
        # Create template
        template = PromptTemplate(
            name=name,
            template_content=template_content,
            metadata=template_metadata,
            template_type=template_type
        )
        
        # Add to templates
        self.templates[name] = template
        
        # Save to disk if requested
        if save_to_disk:
            self._save_template_to_disk(template)
        
        self.logger.info(f"Created template: {name}")
        return template
    
    def update_template(
        self,
        name: str,
        template_content: str = None,
        metadata_updates: Dict[str, Any] = None,
        save_to_disk: bool = True
    ) -> PromptTemplate:
        """Update existing template"""
        if name not in self.templates:
            raise TemplateNotFoundError(f"Template not found: {name}")
        
        template = self.templates[name]
        
        # Update content if provided
        if template_content is not None:
            template.template_content = template_content
            # Recreate Jinja2 template
            if template.template_type == "jinja2":
                template.template = Environment().from_string(template_content)
        
        # Update metadata if provided
        if metadata_updates:
            for key, value in metadata_updates.items():
                if hasattr(template.metadata, key):
                    setattr(template.metadata, key, value)
            
            # Always update the updated_at timestamp
            template.metadata.updated_at = datetime.now()
        
        # Save to disk if requested
        if save_to_disk:
            self._save_template_to_disk(template)
        
        self.logger.info(f"Updated template: {name}")
        return template
    
    def delete_template(self, name: str, delete_from_disk: bool = False):
        """Delete template"""
        if name not in self.templates:
            raise TemplateNotFoundError(f"Template not found: {name}")
        
        template = self.templates[name]
        
        # Delete from disk if requested
        if delete_from_disk:
            template_file = self._get_template_file_path(name)
            if template_file.exists():
                template_file.unlink()
        
        # Remove from memory
        del self.templates[name]
        
        self.logger.info(f"Deleted template: {name}")
    
    def search_templates(
        self,
        query: str = None,
        tags: List[str] = None,
        author: str = None,
        model_type: str = None
    ) -> List[PromptTemplate]:
        """Search templates by various criteria"""
        results = []
        
        for template in self.templates.values():
            # Query search (in name, description)
            if query:
                query_lower = query.lower()
                if (query_lower not in template.name.lower() and 
                    query_lower not in template.metadata.description.lower()):
                    continue
            
            # Tag filter
            if tags:
                if not any(tag in template.metadata.tags for tag in tags):
                    continue
            
            # Author filter
            if author:
                if template.metadata.author != author:
                    continue
            
            # Model type filter
            if model_type:
                required_models = template.metadata.model_requirements
                if model_type not in required_models:
                    continue
            
            results.append(template)
        
        return results
    
    def get_template_metadata(self, name: str) -> PromptMetadata:
        """Get template metadata"""
        template = self.get_template(name)
        return template.metadata
    
    def validate_template(self, name: str, test_variables: Dict[str, Any] = None) -> Dict[str, Any]:
        """Validate template syntax and requirements"""
        template = self.get_template(name)
        validation_result = {
            "valid": True,
            "errors": [],
            "warnings": []
        }
        
        try:
            # Test rendering with provided variables or empty dict
            test_vars = test_variables or {}
            
            # Add dummy values for required variables not provided
            for var in template.metadata.variables:
                if var not in test_vars:
                    test_vars[var] = f"<{var}>"
            
            rendered = template.render(test_vars)
            
            # Check for unrendered variables
            if "<" in rendered and ">" in rendered:
                validation_result["warnings"].append("Template may have unrendered variables")
            
        except Exception as e:
            validation_result["valid"] = False
            validation_result["errors"].append(f"Template rendering failed: {str(e)}")
        
        return validation_result
    
    def export_templates(self, output_file: str, template_names: List[str] = None):
        """Export templates to JSON file"""
        templates_to_export = template_names or list(self.templates.keys())
        
        export_data = {
            "export_timestamp": datetime.now().isoformat(),
            "templates": {}
        }
        
        for name in templates_to_export:
            if name in self.templates:
                export_data["templates"][name] = self.templates[name].to_dict()
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False, default=str)
        
        self.logger.info(f"Exported {len(templates_to_export)} templates to {output_file}")
    
    def import_templates(self, input_file: str, overwrite: bool = False):
        """Import templates from JSON file"""
        with open(input_file, 'r', encoding='utf-8') as f:
            import_data = json.load(f)
        
        templates_data = import_data.get("templates", {})
        imported_count = 0
        
        for name, template_data in templates_data.items():
            if name in self.templates and not overwrite:
                self.logger.warning(f"Template {name} already exists, skipping")
                continue
            
            # Recreate metadata
            metadata_dict = template_data["metadata"]
            metadata = PromptMetadata(
                name=metadata_dict["name"],
                version=metadata_dict["version"],
                description=metadata_dict["description"],
                author=metadata_dict["author"],
                created_at=datetime.fromisoformat(metadata_dict["created_at"]),
                updated_at=datetime.fromisoformat(metadata_dict["updated_at"]),
                tags=metadata_dict["tags"],
                variables=metadata_dict["variables"],
                model_requirements=metadata_dict["model_requirements"],
                usage_examples=metadata_dict["usage_examples"]
            )
            
            # Create template
            template = PromptTemplate(
                name=template_data["name"],
                template_content=template_data["template_content"],
                metadata=metadata,
                template_type=template_data["template_type"]
            )
            
            self.templates[name] = template
            imported_count += 1
        
        self.logger.info(f"Imported {imported_count} templates from {input_file}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get template manager statistics"""
        stats = {
            "total_templates": len(self.templates),
            "template_types": {},
            "authors": {},
            "tags": {},
            "avg_variables_per_template": 0
        }
        
        total_variables = 0
        
        for template in self.templates.values():
            # Template types
            template_type = template.template_type
            stats["template_types"][template_type] = stats["template_types"].get(template_type, 0) + 1
            
            # Authors
            author = template.metadata.author
            stats["authors"][author] = stats["authors"].get(author, 0) + 1
            
            # Tags
            for tag in template.metadata.tags:
                stats["tags"][tag] = stats["tags"].get(tag, 0) + 1
            
            # Variables
            total_variables += len(template.metadata.variables)
        
        if len(self.templates) > 0:
            stats["avg_variables_per_template"] = total_variables / len(self.templates)
        
        return stats
    
    def _save_template_to_disk(self, template: PromptTemplate):
        """Save template to disk in YAML format"""
        template_file = self._get_template_file_path(template.name)
        template_file.parent.mkdir(parents=True, exist_ok=True)
        
        template_data = {
            "metadata": asdict(template.metadata),
            "template": template.template_content,
            "type": template.template_type
        }
        
        with open(template_file, 'w', encoding='utf-8') as f:
            yaml.dump(template_data, f, default_flow_style=False, allow_unicode=True)
    
    def _get_template_file_path(self, template_name: str) -> Path:
        """Get file path for template"""
        # Use first template directory for saving
        template_dir = Path(self.template_directories[0])
        return template_dir / f"{template_name}.yaml"


# Global template manager instance
_template_manager = None


def get_template_manager(agent_name: str = None) -> PromptTemplateManager:
    """
    Get template manager instance for specific agent
    
    Args:
        agent_name: Name of the agent (e.g., 'image_generator', 'video_generator')
                   If None, returns global instance with all templates
    
    Returns:
        PromptTemplateManager instance configured for the agent
    """
    # For agent-specific managers, always create new instance
    # This ensures proper isolation between agents
    if agent_name:
        return PromptTemplateManager(agent_name=agent_name)
    
    # For backward compatibility, maintain global instance
    global _template_manager
    if _template_manager is None:
        _template_manager = PromptTemplateManager()
    return _template_manager


def reset_template_manager():
    """Reset global template manager instance (for reloading)"""
    global _template_manager
    _template_manager = None


def render_prompt(name: str, variables: Dict[str, Any]) -> str:
    """Convenience function to render template"""
    manager = get_template_manager()
    return manager.render_template(name, variables)


def list_available_templates() -> List[str]:
    """Convenience function to list templates"""
    manager = get_template_manager()
    return manager.list_templates()