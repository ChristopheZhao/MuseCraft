from app.main import app

project_routes = [
      (route.path, sorted(route.methods))
      for route in app.routes
      if "/api/v1/projects" in route.path
  ]

print(project_routes)