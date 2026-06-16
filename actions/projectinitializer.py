#!/usr/bin/env python3
"""
Universal Project Initializer Action for Jarvis
Supports: Python, Node, React, Vue, Next.js, Nuxt, Angular, Svelte,
          FastAPI, Django, Flask, Go, Rust, Java (Maven/Gradle), Kotlin,
          C/C++, C#/.NET, PHP (Laravel/Symfony), Ruby (Rails), Swift,
          Flutter/Dart, React Native, Electron, MySQL, PostgreSQL,
          MongoDB, Redis, Docker, Terraform, and more.
"""

import os
import shutil
import subprocess

import shlex

def ok(msg):    print(f"✅ {msg}")
def warn(msg):  print(f"⚠️  {msg}")
def err(msg):   print(f"❌ {msg}")
def info(msg):  print(f"➜  {msg}")

def run(cmd, cwd=None, check=False):
    """Run a shell command, return True on success."""
    try:
        if isinstance(cmd, str):
            cmd_list = shlex.split(cmd)
        else:
            cmd_list = cmd
        result = subprocess.run(
            cmd_list, cwd=cwd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        if result.returncode != 0 and check:
            err(f"Command failed: {cmd}")
            err(result.stderr.strip())
            return False
        return True
    except Exception as e:
        err(str(e))
        return False

def has(tool):
    """Check if a CLI tool is available."""
    return shutil.which(tool) is not None

def mkdir(path):
    os.makedirs(path, exist_ok=True)

def write(path, content=""):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        f.write(content)

def git_init(path):
    if has("git"):
        run("git init", cwd=path)
        ok("Git initialized")
    else:
        warn("git not found, skipping git init")

# ─────────────────────────────────────────────
# COMMON FILES
# ─────────────────────────────────────────────
GITIGNORE = {
    "python":   "__pycache__/\n*.pyc\n*.pyo\n.env\nvenv/\n.venv/\ndist/\nbuild/\n*.egg-info/\n.pytest_cache/\n",
    "node":     "node_modules/\ndist/\nbuild/\n.env\n.env.local\n*.log\n.DS_Store\n",
    "rust":     "target/\nCargo.lock\n*.rs.bk\n",
    "go":       "*.exe\n*.test\nvendor/\n",
    "java":     "*.class\n*.jar\ntarget/\nbuild/\n.gradle/\n*.iml\n.idea/\n",
    "csharp":   "bin/\nobj/\n*.user\n.vs/\n*.suo\n",
    "php":      "vendor/\n.env\ncomposer.lock\n*.log\n",
    "ruby":     ".bundle/\nvendor/bundle/\nGemfile.lock\n*.log\n",
    "swift":    ".build/\n*.xcuserstate\n*.xcworkspace/xcuserdata/\nDerivedData/\n",
    "flutter":  ".dart_tool/\nbuild/\n*.g.dart\n.flutter-plugins\n.flutter-plugins-dependencies\n",
    "c":        "*.o\n*.a\n*.so\n*.out\nbuild/\n",
    "docker":   ".env\n*.log\n",
    "terraform":"*.tfstate\n*.tfstate.backup\n.terraform/\n*.tfvars\n",
    "general":  ".DS_Store\n*.log\n.env\n*.tmp\n",
}

README = lambda name, desc: f"# {name}\n\n{desc}\n\n## Getting Started\n\n```bash\n# Add setup instructions here\n```\n"

# ─────────────────────────────────────────────
# INITIALIZERS
# ─────────────────────────────────────────────

def init_python(name):
    """Plain Python project with venv + tests."""
    mkdir(f"{name}/src")
    mkdir(f"{name}/tests")
    write(f"{name}/src/__init__.py")
    write(f"{name}/tests/__init__.py")
    write(f"{name}/main.py", 'def main():\n    print("Hello, World!")\n\nif __name__ == "__main__":\n    main()\n')
    write(f"{name}/requirements.txt", "# Add your dependencies here\n")
    write(f"{name}/requirements-dev.txt", "pytest\nblack\nflake8\n")
    write(f"{name}/.gitignore", GITIGNORE["python"])
    write(f"{name}/README.md", README(name, "A Python project."))
    write(f"{name}/.env.example", "# Copy to .env and fill in values\nDEBUG=true\n")
    if has("python3"):
        run("python3 -m venv venv", cwd=name)
        ok("Virtual environment created (venv/)")
    else:
        warn("python3 not found, skipping venv")
    git_init(name)

def init_fastapi(name):
    """FastAPI project with routers, models, tests."""
    for d in ["app/routers", "app/models", "app/schemas", "app/core", "tests"]:
        mkdir(f"{name}/{d}")
    write(f"{name}/app/__init__.py")
    write(f"{name}/app/main.py",
        'from fastapi import FastAPI\nfrom app.routers import items\n\napp = FastAPI(title="My API")\napp.include_router(items.router)\n\n@app.get("/")\ndef root():\n    return {"message": "Hello World"}\n')
    write(f"{name}/app/routers/__init__.py")
    write(f"{name}/app/routers/items.py",
        'from fastapi import APIRouter\n\nrouter = APIRouter(prefix="/items", tags=["items"])\n\n@router.get("/")\ndef get_items():\n    return []\n')
    write(f"{name}/app/models/__init__.py")
    write(f"{name}/app/core/config.py",
        'from pydantic_settings import BaseSettings\n\nclass Settings(BaseSettings):\n    app_name: str = "My API"\n    debug: bool = False\n\nsettings = Settings()\n')
    write(f"{name}/requirements.txt", "fastapi\nuvicorn[standard]\npydantic-settings\n")
    write(f"{name}/requirements-dev.txt", "pytest\nhttpx\n")
    write(f"{name}/.gitignore", GITIGNORE["python"])
    write(f"{name}/README.md", README(name, "A FastAPI project."))
    write(f"{name}/.env.example", "DEBUG=false\n")
    if has("python3"):
        run("python3 -m venv venv", cwd=name)
    git_init(name)

def init_django(name):
    if not has("django-admin"):
        warn("django-admin not found. Installing Django...")
        run("pip install django")
    run(f"django-admin startproject {name} .")
    write(f"{name}/.gitignore", GITIGNORE["python"])
    write(f"{name}/requirements.txt", "django\ndjango-environ\n")
    write(f"{name}/README.md", README(name, "A Django project."))
    git_init(name)

def init_flask(name):
    for d in ["app/templates", "app/static", "tests"]:
        mkdir(f"{name}/{d}")
    write(f"{name}/app/__init__.py",
        'from flask import Flask\n\ndef create_app():\n    app = Flask(__name__)\n\n    @app.route("/")\n    def index():\n        return "Hello World!"\n\n    return app\n')
    write(f"{name}/run.py", 'from app import create_app\n\napp = create_app()\n\nif __name__ == "__main__":\n    app.run(debug=True)\n')
    write(f"{name}/requirements.txt", "flask\npython-dotenv\n")
    write(f"{name}/.gitignore", GITIGNORE["python"])
    write(f"{name}/README.md", README(name, "A Flask project."))
    git_init(name)

def init_node(name):
    mkdir(f"{name}/src")
    write(f"{name}/src/index.js", 'console.log("Hello, World!");\n')
    write(f"{name}/.gitignore", GITIGNORE["node"])
    write(f"{name}/README.md", README(name, "A Node.js project."))
    if has("npm"):
        run("npm init -y", cwd=name)
        ok("npm initialized")
    else:
        warn("npm not found")
    git_init(name)

def init_react(name):
    if has("npm"):
        info("Creating React app via Vite...")
        run(f"npm create vite@latest {name} -- --template react", cwd=".")
        ok("React (Vite) project created")
    else:
        err("npm not found. Install Node.js first.")
        return
    git_init(name)

def init_react_ts(name):
    if has("npm"):
        run(f"npm create vite@latest {name} -- --template react-ts", cwd=".")
        ok("React + TypeScript (Vite) project created")
    else:
        err("npm not found")
        return
    git_init(name)

def init_nextjs(name):
    if has("npx"):
        run(f"npx create-next-app@latest {name} --yes", cwd=".")
        ok("Next.js project created")
    else:
        err("npx not found")

def init_vue(name):
    if has("npm"):
        run(f"npm create vite@latest {name} -- --template vue", cwd=".")
        ok("Vue 3 (Vite) project created")
    else:
        err("npm not found")

def init_nuxt(name):
    if has("npx"):
        run(f"npx nuxi@latest init {name}", cwd=".")
        ok("Nuxt 3 project created")
    else:
        err("npx not found")

def init_angular(name):
    if has("ng"):
        run(f"ng new {name} --routing --style=scss", cwd=".")
        ok("Angular project created")
    elif has("npx"):
        run(f"npx @angular/cli new {name} --routing --style=scss", cwd=".")
        ok("Angular project created via npx")
    else:
        err("npm/ng not found")

def init_svelte(name):
    if has("npm"):
        run(f"npm create svelte@latest {name}", cwd=".")
        ok("SvelteKit project created")
    else:
        err("npm not found")

def init_electron(name):
    mkdir(f"{name}/src")
    write(f"{name}/src/main.js",
        "const { app, BrowserWindow } = require('electron');\n\nfunction createWindow() {\n  const win = new BrowserWindow({ width: 800, height: 600 });\n  win.loadFile('src/index.html');\n}\n\napp.whenReady().then(createWindow);\n")
    write(f"{name}/src/index.html",
        "<!DOCTYPE html>\n<html>\n<head><title>Electron App</title></head>\n<body>\n  <h1>Hello from Electron!</h1>\n</body>\n</html>\n")
    write(f"{name}/package.json",
        f'{{\n  "name": "{name}",\n  "version": "1.0.0",\n  "main": "src/main.js",\n  "scripts": {{\n    "start": "electron ."\n  }},\n  "devDependencies": {{\n    "electron": "^latest"\n  }}\n}}\n')
    write(f"{name}/.gitignore", GITIGNORE["node"])
    git_init(name)

def init_express(name):
    for d in ["src/routes", "src/controllers", "src/middleware", "src/models"]:
        mkdir(f"{name}/{d}")
    write(f"{name}/src/app.js",
        "const express = require('express');\nconst app = express();\n\napp.use(express.json());\n\napp.get('/', (req, res) => res.json({ message: 'Hello World' }));\n\nmodule.exports = app;\n")
    write(f"{name}/src/server.js",
        "const app = require('./app');\nconst PORT = process.env.PORT || 3000;\napp.listen(PORT, () => console.log(`Server running on port ${PORT}`));\n")
    write(f"{name}/.gitignore", GITIGNORE["node"])
    write(f"{name}/.env.example", "PORT=3000\n")
    write(f"{name}/README.md", README(name, "An Express.js REST API."))
    if has("npm"):
        run("npm init -y", cwd=name)
        run("npm install express dotenv", cwd=name)
    git_init(name)

def init_go(name):
    mkdir(f"{name}/cmd/{name}")
    mkdir(f"{name}/internal")
    mkdir(f"{name}/pkg")
    write(f"{name}/cmd/{name}/main.go",
        f'package main\n\nimport "fmt"\n\nfunc main() {{\n\tfmt.Println("Hello, {name}!")\n}}\n')
    write(f"{name}/.gitignore", GITIGNORE["go"])
    write(f"{name}/README.md", README(name, "A Go project."))
    if has("go"):
        run(f"go mod init {name}", cwd=name)
        ok("go.mod initialized")
    else:
        warn("go not found")
    git_init(name)

def init_rust(name):
    if has("cargo"):
        run(f"cargo new {name}", cwd=".")
        ok("Rust project created via cargo")
    else:
        err("cargo not found. Install Rust from https://rustup.rs")
        return
    git_init(name)

def init_rust_lib(name):
    if has("cargo"):
        run(f"cargo new {name} --lib", cwd=".")
        ok("Rust library created")
    else:
        err("cargo not found")

def init_java_maven(name):
    group = "com.example"
    if has("mvn"):
        run(f"mvn archetype:generate -DgroupId={group} -DartifactId={name} "
            f"-DarchetypeArtifactId=maven-archetype-quickstart -DinteractiveMode=false", cwd=".")
        ok("Java Maven project created")
    else:
        err("mvn not found. Install Maven first.")
        pkg_path = f"{name}/src/main/java/{group.replace('.','/')}"
        mkdir(pkg_path)
        mkdir(f"{name}/src/test/java/{group.replace('.','/')}")
        write(f"{pkg_path}/App.java",
            f'package {group};\n\npublic class App {{\n    public static void main(String[] args) {{\n        System.out.println("Hello World!");\n    }}\n}}\n')
        write(f"{name}/pom.xml",
            f'<project>\n  <modelVersion>4.0.0</modelVersion>\n  <groupId>{group}</groupId>\n  <artifactId>{name}</artifactId>\n  <version>1.0-SNAPSHOT</version>\n</project>\n')
        write(f"{name}/.gitignore", GITIGNORE["java"])

def init_java_gradle(name):
    if has("gradle"):
        mkdir(name)
        run("gradle init --type java-application --dsl groovy", cwd=name)
        ok("Java Gradle project created")
    else:
        err("gradle not found. Install Gradle or use Maven instead.")

def init_kotlin(name):
    if has("gradle"):
        mkdir(name)
        run("gradle init --type kotlin-application --dsl kotlin", cwd=name)
        ok("Kotlin Gradle project created")
    else:
        src = f"{name}/src/main/kotlin"
        mkdir(src)
        write(f"{src}/Main.kt", 'fun main() {\n    println("Hello, World!")\n}\n')
        write(f"{name}/.gitignore", GITIGNORE["java"])
        warn("gradle not found — scaffolded manually")
    git_init(name)

def init_csharp(name):
    if has("dotnet"):
        run(f"dotnet new console -n {name} -o {name}", cwd=".")
        ok("C# .NET console project created")
    else:
        err("dotnet not found.")
    write(f"{name}/.gitignore", GITIGNORE["csharp"])
    git_init(name)

def init_aspnet(name):
    if has("dotnet"):
        run(f"dotnet new webapi -n {name} -o {name}", cwd=".")
        ok("ASP.NET Web API project created")
    else:
        err("dotnet not found")

def init_unity(name):
    for d in ["Assets/Scripts", "Assets/Scenes", "Assets/Prefabs", "ProjectSettings", "Packages"]:
        mkdir(f"{name}/{d}")
    write(f"{name}/Assets/Scripts/GameManager.cs",
        'using UnityEngine;\n\npublic class GameManager : MonoBehaviour\n{\n    void Start() { }\n    void Update() { }\n}\n')
    write(f"{name}/.gitignore",
        "Library/\nTemp/\nObj/\nBuild/\nBuilds/\n*.csproj\n*.unityproj\n*.sln\n*.suo\n*.user\n*.pidb\n*.booproj\n*.svd\n")
    write(f"{name}/README.md", README(name, "A Unity project. Open with Unity Hub."))
    warn("Open this folder with Unity Hub to finish setup.")
    git_init(name)

def init_cpp(name):
    mkdir(f"{name}/src")
    mkdir(f"{name}/include")
    mkdir(f"{name}/build")
    write(f"{name}/src/main.cpp",
        '#include <iostream>\n\nint main() {\n    std::cout << "Hello, World!" << std::endl;\n    return 0;\n}\n')
    write(f"{name}/CMakeLists.txt",
        f"cmake_minimum_required(VERSION 3.15)\nproject({name})\nset(CMAKE_CXX_STANDARD 17)\nadd_executable({name} src/main.cpp)\n")
    write(f"{name}/.gitignore", GITIGNORE["c"])
    write(f"{name}/README.md", README(name, "A C++ project with CMake."))
    git_init(name)

def init_c(name):
    mkdir(f"{name}/src")
    mkdir(f"{name}/include")
    write(f"{name}/src/main.c",
        '#include <stdio.h>\n\nint main() {\n    printf("Hello, World!\\n");\n    return 0;\n}\n')
    write(f"{name}/Makefile",
        f"CC=gcc\nCFLAGS=-Wall -Wextra\nTARGET={name}\n\nall:\n\t$(CC) $(CFLAGS) -o $(TARGET) src/main.c\n\nclean:\n\trm -f $(TARGET)\n")
    write(f"{name}/.gitignore", GITIGNORE["c"])
    git_init(name)

def init_php_laravel(name):
    if has("composer"):
        run(f"composer create-project laravel/laravel {name}", cwd=".")
        ok("Laravel project created")
    else:
        err("composer not found. Install from https://getcomposer.org")
    git_init(name)

def init_php_symfony(name):
    if has("symfony"):
        run(f"symfony new {name} --webapp", cwd=".")
        ok("Symfony project created")
    elif has("composer"):
        run(f"composer create-project symfony/skeleton {name}", cwd=".")
        ok("Symfony skeleton created")
    else:
        err("composer not found")

def init_php_plain(name):
    mkdir(f"{name}/public")
    mkdir(f"{name}/src")
    write(f"{name}/public/index.php", "<?php\necho 'Hello, World!';\n")
    write(f"{name}/composer.json",
        f'{{\n  "name": "app/{name}",\n  "autoload": {{\n    "psr-4": {{\n      "App\\\\": "src/"\n    }}\n  }}\n}}\n')
    write(f"{name}/.gitignore", GITIGNORE["php"])
    git_init(name)

def init_ruby_rails(name):
    if has("rails"):
        run(f"rails new {name}", cwd=".")
        ok("Rails project created")
    else:
        err("rails not found. Run: gem install rails")

def init_ruby_plain(name):
    mkdir(f"{name}/lib")
    mkdir(f"{name}/spec")
    write(f"{name}/lib/{name}.rb", 'puts "Hello, World!"\n')
    write(f"{name}/Gemfile", 'source "https://rubygems.org"\nruby "~> 3.0"\n\ngroup :development, :test do\n  gem "rspec"\nend\n')
    write(f"{name}/.gitignore", GITIGNORE["ruby"])
    git_init(name)

def init_swift(name):
    if has("swift"):
        run(f"swift package init --name {name}", cwd=name)
        ok("Swift package created")
    else:
        mkdir(f"{name}/Sources/{name}")
        write(f"{name}/Sources/{name}/main.swift", 'print("Hello, World!")\n')
        write(f"{name}/Package.swift",
            f'// swift-tools-version:5.9\nimport PackageDescription\n\nlet package = Package(\n    name: "{name}",\n    targets: [\n        .executableTarget(name: "{name}", path: "Sources/{name}")\n    ]\n)\n')
        write(f"{name}/.gitignore", GITIGNORE["swift"])
        warn("swift CLI not found — scaffolded manually")
    git_init(name)

def init_flutter(name):
    if has("flutter"):
        run(f"flutter create {name}", cwd=".")
        ok("Flutter project created")
    else:
        err("flutter not found.")
    git_init(name)

def init_dart(name):
    if has("dart"):
        run(f"dart create {name}", cwd=".")
        ok("Dart project created")
    else:
        mkdir(f"{name}/bin")
        write(f"{name}/bin/{name}.dart", 'void main() {\n  print("Hello, World!");\n}\n')
        write(f"{name}/pubspec.yaml",
            f"name: {name}\ndescription: A Dart project.\nversion: 1.0.0\nenvironment:\n  sdk: '>=3.0.0 <4.0.0'\n")
        write(f"{name}/.gitignore", GITIGNORE["flutter"])
        warn("dart CLI not found — scaffolded manually")
    git_init(name)

def init_react_native(name):
    if has("npx"):
        run(f"npx react-native@latest init {name}", cwd=".")
        ok("React Native project created")
    else:
        err("npx not found")

def init_mysql(name):
    mkdir(f"{name}/schema")
    mkdir(f"{name}/seeds")
    mkdir(f"{name}/migrations")
    mkdir(f"{name}/queries")
    write(f"{name}/schema/001_init.sql",
        f"-- {name} Database Schema\nCREATE DATABASE IF NOT EXISTS `{name}`;\nUSE `{name}`;\n\nCREATE TABLE IF NOT EXISTS users (\n    id INT AUTO_INCREMENT PRIMARY KEY,\n    name VARCHAR(100) NOT NULL,\n    email VARCHAR(255) UNIQUE NOT NULL,\n    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP\n);\n")
    write(f"{name}/seeds/001_seed.sql",
        f"USE `{name}`;\nINSERT INTO users (name, email) VALUES\n  ('Alice', 'alice@example.com'),\n  ('Bob', 'bob@example.com');\n")
    write(f"{name}/migrations/README.md", "# Migrations\nRun files in order: 001_, 002_, etc.\n")
    write(f"{name}/queries/sample.sql",
        f"USE `{name}`;\n\n-- Get all users\nSELECT * FROM users;\n\n-- Find by email\nSELECT * FROM users WHERE email = 'alice@example.com';\n")
    write(f"{name}/.env.example",
        f"DB_HOST=localhost\nDB_PORT=3306\nDB_NAME={name}\nDB_USER=root\nDB_PASS=\n")
    write(f"{name}/README.md",
        f"# {name} MySQL Project\n\n## Setup\n```bash\nmysql -u root -p < schema/001_init.sql\nmysql -u root -p < seeds/001_seed.sql\n```\n")
    git_init(name)

def init_postgres(name):
    mkdir(f"{name}/schema")
    mkdir(f"{name}/seeds")
    mkdir(f"{name}/migrations")
    write(f"{name}/schema/001_init.sql",
        f"-- {name} Schema\nCREATE TABLE IF NOT EXISTS users (\n    id SERIAL PRIMARY KEY,\n    name VARCHAR(100) NOT NULL,\n    email VARCHAR(255) UNIQUE NOT NULL,\n    created_at TIMESTAMPTZ DEFAULT NOW()\n);\n")
    write(f"{name}/seeds/001_seed.sql",
        "INSERT INTO users (name, email) VALUES\n  ('Alice', 'alice@example.com'),\n  ('Bob', 'bob@example.com')\nON CONFLICT DO NOTHING;\n")
    write(f"{name}/.env.example",
        f"DATABASE_URL=postgresql://user:password@localhost:5432/{name}\n")
    write(f"{name}/README.md",
        f"# {name} PostgreSQL Project\n\n## Setup\n```bash\npsql -U postgres -f schema/001_init.sql\npsql -U postgres -d {name} -f seeds/001_seed.sql\n```\n")
    git_init(name)

def init_mongodb(name):
    mkdir(f"{name}/schemas")
    mkdir(f"{name}/seeds")
    mkdir(f"{name}/queries")
    write(f"{name}/schemas/user.js",
        f'// User schema for {name}\ndb = db.getSiblingDB("{name}");\ndb.createCollection("users");\ndb.users.createIndex({{ email: 1 }}, {{ unique: true }});\n')
    write(f"{name}/seeds/users.js",
        f'db = db.getSiblingDB("{name}");\ndb.users.insertMany([\n  {{ name: "Alice", email: "alice@example.com", createdAt: new Date() }},\n  {{ name: "Bob",   email: "bob@example.com",   createdAt: new Date() }}\n]);\n')
    write(f"{name}/.env.example",
        f"MONGODB_URI=mongodb://localhost:27017/{name}\n")
    write(f"{name}/README.md",
        f"# {name} MongoDB Project\n\n## Setup\n```bash\nmongosh < schemas/user.js\nmongosh < seeds/users.js\n```\n")
    git_init(name)

def init_redis(name):
    mkdir(f"{name}/scripts")
    write(f"{name}/scripts/setup.redis",
        "# Redis setup script\nSET greeting 'Hello, World!'\nGET greeting\nSET counter 0\nINCR counter\n")
    write(f"{name}/scripts/example.py",
        "import redis\n\nr = redis.Redis(host='localhost', port=6379, decode_responses=True)\nr.set('name', 'World')\nprint(r.get('name'))\n")
    write(f"{name}/requirements.txt", "redis\n")
    write(f"{name}/.env.example", "REDIS_URL=redis://localhost:6379/0\n")
    write(f"{name}/README.md",
        f"# {name} Redis Project\n\n## Setup\n```bash\nredis-cli < scripts/setup.redis\n```\n")
    git_init(name)

def init_sqlite(name):
    mkdir(f"{name}/db")
    write(f"{name}/db/schema.sql",
        f"-- {name} SQLite Schema\nCREATE TABLE IF NOT EXISTS users (\n    id INTEGER PRIMARY KEY AUTOINCREMENT,\n    name TEXT NOT NULL,\n    email TEXT UNIQUE NOT NULL,\n    created_at TEXT DEFAULT (datetime('now'))\n);\n")
    write(f"{name}/db/seed.sql",
        "INSERT INTO users (name, email) VALUES\n  ('Alice', 'alice@example.com'),\n  ('Bob', 'bob@example.com');\n")
    write(f"{name}/main.py",
        "import sqlite3\n\nconn = sqlite3.connect('db/database.db')\ncur = conn.cursor()\n\nwith open('db/schema.sql') as f:\n    conn.executescript(f.read())\n\ncur.execute('SELECT * FROM users')\nprint(cur.fetchall())\nconn.close()\n")
    write(f"{name}/.gitignore", "*.db\n*.db-journal\n" + GITIGNORE["python"])
    write(f"{name}/README.md", README(name, "A SQLite project."))
    git_init(name)

def init_docker(name):
    write(f"{name}/Dockerfile",
        "FROM python:3.12-slim\nWORKDIR /app\nCOPY requirements.txt .\nRUN pip install -r requirements.txt\nCOPY . .\nCMD [\"python\", \"main.py\"]\n")
    write(f"{name}/docker-compose.yml",
        f"version: '3.8'\n\nservices:\n  app:\n    build: .\n    ports:\n      - '8000:8000'\n    env_file:\n      - .env\n    volumes:\n      - .:/app\n  db:\n    image: postgres:16\n    environment:\n      POSTGRES_DB: {name}\n      POSTGRES_USER: user\n      POSTGRES_PASSWORD: password\n    ports:\n      - '5432:5432'\n")
    write(f"{name}/.dockerignore", "__pycache__/\n*.pyc\n.env\nvenv/\n.git/\n")
    write(f"{name}/.env.example", f"DEBUG=false\nDATABASE_URL=postgresql://user:password@db:5432/{name}\n")
    write(f"{name}/requirements.txt", "")
    write(f"{name}/main.py", 'print("Hello from Docker!")\n')
    write(f"{name}/README.md",
        f"# {name}\n\n## Run\n```bash\ndocker compose up --build\n```\n")
    write(f"{name}/.gitignore", GITIGNORE["docker"] + GITIGNORE["python"])
    git_init(name)

def init_terraform(name):
    for d in ["modules", "environments/dev", "environments/prod"]:
        mkdir(f"{name}/{d}")
    write(f"{name}/main.tf",
        'terraform {\n  required_version = ">= 1.5"\n  required_providers {\n    aws = {\n      source  = "hashicorp/aws"\n      version = "~> 5.0"\n    }\n  }\n}\n\nprovider "aws" {\n  region = var.region\n}\n')
    write(f"{name}/variables.tf",
        f'variable "region" {{\n  type    = string\n  default = "us-east-1"\n}}\n\nvariable "project_name" {{\n  type    = string\n  default = "{name}"\n}}\n')
    write(f"{name}/outputs.tf", "# Add your outputs here\n")
    write(f"{name}/.gitignore", GITIGNORE["terraform"])
    write(f"{name}/README.md",
        f"# {name} Terraform\n\n## Usage\n```bash\nterraform init\nterraform plan\nterraform apply\n```\n")
    git_init(name)

def init_ansible(name):
    for d in ["roles", "group_vars", "host_vars", "inventory"]:
        mkdir(f"{name}/{d}")
    write(f"{name}/inventory/hosts.yml",
        "all:\n  hosts:\n    server1:\n      ansible_host: 192.168.1.10\n")
    write(f"{name}/playbook.yml",
        "---\n- name: Main playbook\n  hosts: all\n  become: yes\n  tasks:\n    - name: Ping\n      ansible.builtin.ping:\n")
    write(f"{name}/ansible.cfg",
        "[defaults]\ninventory = inventory/hosts.yml\nremote_user = ubuntu\n")
    write(f"{name}/README.md", README(name, "An Ansible project."))
    git_init(name)

def init_data_science(name):
    for d in ["data/raw", "data/processed", "notebooks", "src", "models", "reports"]:
        mkdir(f"{name}/{d}")
    write(f"{name}/notebooks/01_exploration.ipynb",
        '{\n "cells": [],\n "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},\n "nbformat": 4,\n "nbformat_minor": 5\n}\n')
    write(f"{name}/src/__init__.py")
    write(f"{name}/src/data.py", "# Data loading and preprocessing\n")
    write(f"{name}/src/features.py", "# Feature engineering\n")
    write(f"{name}/src/model.py", "# Model training and evaluation\n")
    write(f"{name}/requirements.txt",
        "numpy\npandas\nscikit-learn\nmatplotlib\nseaborn\njupyterlab\n")
    write(f"{name}/.gitignore",
        GITIGNORE["python"] + "data/raw/\ndata/processed/\nmodels/\n*.csv\n*.parquet\n")
    write(f"{name}/README.md", README(name, "A Data Science / ML project."))
    git_init(name)

def init_cli_tool(name):
    mkdir(f"{name}/src/{name}")
    write(f"{name}/src/{name}/__init__.py", '__version__ = "0.1.0"\n')
    write(f"{name}/src/{name}/cli.py",
        'import click\n\n@click.group()\ndef cli():\n    """My CLI tool."""\n    pass\n\n@cli.command()\n@click.argument("name")\ndef hello(name):\n    """Say hello."""\n    click.echo(f"Hello, {name}!")\n\nif __name__ == "__main__":\n    cli()\n')
    write(f"{name}/setup.py",
        f'from setuptools import setup, find_packages\n\nsetup(\n    name="{name}",\n    version="0.1.0",\n    packages=find_packages("src"),\n    package_dir={{"": "src"}},\n    install_requires=["click"],\n    entry_points={{\n        "console_scripts": [\n            "{name}={name}.cli:cli",\n        ],\n    }},\n)\n')
    write(f"{name}/requirements.txt", "click\n")
    write(f"{name}/.gitignore", GITIGNORE["python"])
    write(f"{name}/README.md", README(name, "A Python CLI tool."))
    git_init(name)

def init_graphql(name):
    mkdir(f"{name}/src")
    write(f"{name}/src/schema.js",
        'const { gql } = require("apollo-server");\n\nconst typeDefs = gql`\n  type Query {\n    hello: String\n  }\n`;\n\nmodule.exports = typeDefs;\n')
    write(f"{name}/src/resolvers.js",
        'const resolvers = {\n  Query: {\n    hello: () => "Hello from GraphQL!",\n  },\n};\n\nmodule.exports = resolvers;\n')
    write(f"{name}/src/index.js",
        'const { ApolloServer } = require("apollo-server");\nconst typeDefs = require("./schema");\nconst resolvers = require("./resolvers");\n\nconst server = new ApolloServer({ typeDefs, resolvers });\nserver.listen().then(({ url }) => console.log(`🚀 Server at ${url}`));\n')
    write(f"{name}/.gitignore", GITIGNORE["node"])
    write(f"{name}/README.md", README(name, "A GraphQL API with Apollo Server."))
    if has("npm"):
        run("npm init -y", cwd=name)
        run("npm install apollo-server graphql", cwd=name)
    git_init(name)

def init_monorepo(name):
    for d in ["apps/frontend", "apps/backend", "packages/shared", "packages/ui"]:
        mkdir(f"{name}/{d}")
    write(f"{name}/package.json",
        f'{{\n  "name": "{name}",\n  "private": true,\n  "workspaces": ["apps/*", "packages/*"],\n  "scripts": {{\n    "build": "turbo run build",\n    "dev": "turbo run dev"\n  }}\n}}\n')
    write(f"{name}/turbo.json",
        '{\n  "$schema": "https://turbo.build/schema.json",\n  "pipeline": {\n    "build": { "dependsOn": ["^build"] },\n    "dev": { "cache": false }\n  }\n}\n')
    write(f"{name}/.gitignore", GITIGNORE["node"])
    write(f"{name}/README.md", README(name, "A monorepo project."))
    if has("npm"):
        run("npm init -y", cwd=name)
    git_init(name)

# ─────────────────────────────────────────────
# REGISTRY
# ─────────────────────────────────────────────
PROJECTS = {
    "python":         (init_python,       "Plain Python project with venv + tests"),
    "fastapi":        (init_fastapi,      "FastAPI REST API with routers + models"),
    "django":         (init_django,       "Django web framework"),
    "flask":          (init_flask,        "Flask web framework"),
    "data-science":   (init_data_science, "Data Science / ML with Jupyter"),
    "cli":            (init_cli_tool,     "Python CLI tool with Click"),
    "node":           (init_node,         "Node.js plain project"),
    "express":        (init_express,      "Express.js REST API"),
    "react":          (init_react,        "React (Vite)"),
    "react-ts":       (init_react_ts,     "React + TypeScript (Vite)"),
    "nextjs":         (init_nextjs,       "Next.js (React SSR)"),
    "vue":            (init_vue,          "Vue 3 (Vite)"),
    "nuxt":           (init_nuxt,         "Nuxt 3 (Vue SSR)"),
    "angular":        (init_angular,      "Angular"),
    "svelte":         (init_svelte,       "SvelteKit"),
    "electron":       (init_electron,     "Electron desktop app"),
    "graphql":        (init_graphql,      "GraphQL API (Apollo Server)"),
    "monorepo":       (init_monorepo,     "Monorepo (Turborepo)"),
    "flutter":        (init_flutter,      "Flutter mobile/desktop app"),
    "dart":           (init_dart,         "Dart console app"),
    "react-native":   (init_react_native, "React Native mobile app"),
    "go":             (init_go,           "Go module project"),
    "rust":           (init_rust,         "Rust binary (cargo)"),
    "rust-lib":       (init_rust_lib,     "Rust library crate"),
    "cpp":            (init_cpp,          "C++ with CMake"),
    "c":              (init_c,            "C with Makefile"),
    "swift":          (init_swift,        "Swift package"),
    "kotlin":         (init_kotlin,       "Kotlin + Gradle"),
    "java-maven":     (init_java_maven,   "Java with Maven"),
    "java-gradle":    (init_java_gradle,  "Java with Gradle"),
    "csharp":         (init_csharp,       "C# .NET console app"),
    "aspnet":         (init_aspnet,       "ASP.NET Web API"),
    "unity":          (init_unity,        "Unity game project stub"),
    "laravel":        (init_php_laravel,  "Laravel PHP framework"),
    "symfony":        (init_php_symfony,  "Symfony PHP framework"),
    "php":            (init_php_plain,    "Plain PHP project"),
    "rails":          (init_ruby_rails,   "Ruby on Rails"),
    "ruby":           (init_ruby_plain,   "Plain Ruby project"),
    "mysql":          (init_mysql,        "MySQL database project"),
    "postgres":       (init_postgres,     "PostgreSQL database project"),
    "mongodb":        (init_mongodb,      "MongoDB project"),
    "redis":          (init_redis,        "Redis project"),
    "sqlite":         (init_sqlite,       "SQLite project"),
    "docker":         (init_docker,       "Docker + Compose project"),
    "terraform":      (init_terraform,    "Terraform infrastructure"),
    "ansible":        (init_ansible,      "Ansible playbook project"),
}

# ─────────────────────────────────────────────
# Jarvis Action Handler
# ─────────────────────────────────────────────
def handle(parameters: dict | None = None, **kwargs) -> str:
    p = parameters or {}
    ptype = p.get("project_type", "").strip().lower()
    name = p.get("project_name", "").strip()

    if not ptype or ptype not in PROJECTS:
        types = ", ".join(sorted(PROJECTS.keys()))
        return f"Unknown or missing project_type '{ptype}'. Available: {types}"

    if not name:
        return "Project_name cannot be empty."

    # Allow setting a specific workspace directory via parameters
    workspace = p.get("workspace", ".")
    target_path = os.path.join(workspace, name)

    if os.path.exists(target_path):
        return f"Folder '{target_path}' already exists!"

    # Save original cwd and change to workspace dir so the CLI scripts work correctly
    original_cwd = os.getcwd()
    os.makedirs(workspace, exist_ok=True)
    os.chdir(workspace)

    try:
        # CLI tools that create the root dir themselves
        NO_PREMKDIR = {"react", "react-ts", "nextjs", "vue", "nuxt", "angular",
                       "svelte", "react-native", "flutter", "rust", "rust-lib",
                       "django", "laravel", "symfony", "rails", "dart"}

        if ptype not in NO_PREMKDIR:
            mkdir(name)

        fn, desc = PROJECTS[ptype]
        fn(name)
        
        return f"Successfully initialized {desc} at '{target_path}'."
    except Exception as e:
        return f"Error initializing project: {e}"
    finally:
        os.chdir(original_cwd)
