#!/usr/bin/env python
"""EvolveRFC MCP Server - 自动启动的 HTTP MCP Server

当运行 EvolveRFC 主命令时，MCP Server 会自动在后台启动。
其他 AI 助手可以通过 HTTP 调用 MCP API。

使用方法:
    # 运行工作流（自动启动 MCP）
    uv run python -m evolve_rfc.workflow

    # 其他 AI 助手调用示例:
    curl -X POST http://localhost:8888/mcp/call \
      -H "Content-Type: application/json" \
      -d '{"tool": "read", "arguments": {"file_path": "rfcs/example.md"}}'
"""
import asyncio
from typing import Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

from .server import MCPTools
from ..settings import get_settings

# MCP Server 配置（从全局配置读取）
def get_mcp_config():
    settings = get_settings()
    return settings.mcp.host, settings.mcp.port

# 全局服务器引用
_server_instance = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global _server_instance
    mcp_host, mcp_port = get_mcp_config()
    print(f"🚀 EvolveRFC MCP Server 已启动: http://{mcp_host}:{mcp_port}")
    print("📋 可用工具:")
    print("   - read: 读取文件内容")
    print("   - read_regex: 读取文件并用正则过滤")
    print("   - list: 列出目录文件")
    print("   - list_regex: 列出目录文件（正则过滤）")
    print("   - find: 递归查找文件")
    print("   - find_regex: 递归查找文件（正则过滤）")
    yield
    print("🛑 EvolveRFC MCP Server 已关闭")


app = FastAPI(
    title="EvolveRFC MCP Server",
    description="提供文件操作工具，让其他 AI 助手可以读取文件和搜索代码",
    lifespan=lifespan,
)


class ToolListResponse(BaseModel):
    """工具列表响应"""
    tools: list[dict]


class ToolCallRequest(BaseModel):
    """工具调用请求"""
    tool: str
    arguments: dict[str, Any] = {}


class ToolCallResponse(BaseModel):
    """工具调用响应"""
    result: str


@app.get("/mcp/tools", response_model=ToolListResponse)
async def list_tools():
    """列出所有可用的工具"""
    return {
        "tools": [
            {
                "name": "read",
                "description": "读取文件内容",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "文件路径"},
                        "limit": {"type": "integer", "description": "最大读取字符数", "default": 10000},
                    },
                    "required": ["file_path"],
                },
            },
            {
                "name": "read_regex",
                "description": "读取文件并用正则过滤内容",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "文件路径"},
                        "pattern": {"type": "string", "description": "正则表达式"},
                        "first_match": {"type": "boolean", "description": "只返回第一个匹配", "default": False},
                    },
                    "required": ["file_path", "pattern"],
                },
            },
            {
                "name": "list",
                "description": "列出目录下的文件",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "dir_path": {"type": "string", "description": "目录路径", "default": "."},
                        "pattern": {"type": "string", "description": "文件匹配模式", "default": "*"},
                        "max_count": {"type": "integer", "description": "最大返回数量", "default": 50},
                    },
                },
            },
            {
                "name": "list_regex",
                "description": "列出目录下的文件（用正则过滤文件名）",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "dir_path": {"type": "string", "description": "目录路径", "default": "."},
                        "pattern": {"type": "string", "description": "文件名正则表达式", "default": ".*"},
                        "max_count": {"type": "integer", "description": "最大返回数量", "default": 50},
                    },
                },
            },
            {
                "name": "find",
                "description": "递归查找文件",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "start_dir": {"type": "string", "description": "起始目录", "default": "."},
                        "pattern": {"type": "string", "description": "文件匹配模式", "default": "*"},
                        "max_count": {"type": "integer", "description": "最大返回数量", "default": 50},
                    },
                },
            },
            {
                "name": "find_regex",
                "description": "递归查找文件（用正则过滤路径）",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "start_dir": {"type": "string", "description": "起始目录", "default": "."},
                        "pattern": {"type": "string", "description": "路径正则表达式", "default": ".*"},
                        "max_count": {"type": "integer", "description": "最大返回数量", "default": 50},
                    },
                },
            },
        ]
    }


@app.post("/mcp/call", response_model=ToolCallResponse)
async def call_tool(request: ToolCallRequest):
    """调用工具"""
    try:
        tool_name = request.tool
        args = request.arguments

        if tool_name == "read":
            result = MCPTools.read(args["file_path"], args.get("limit", 10000))
        elif tool_name == "read_regex":
            result = MCPTools.read_regex(args["file_path"], args["pattern"], args.get("first_match", False))
        elif tool_name == "list":
            result = MCPTools.list(args.get("dir_path", "."), args.get("pattern", "*"), args.get("max_count", 50))
        elif tool_name == "list_regex":
            result = MCPTools.list_regex(args.get("dir_path", "."), args.get("pattern", ".*"), args.get("max_count", 50))
        elif tool_name == "find":
            result = MCPTools.find(args.get("start_dir", "."), args.get("pattern", "*"), args.get("max_count", 50))
        elif tool_name == "find_regex":
            result = MCPTools.find_regex(args.get("start_dir", "."), args.get("pattern", ".*"), args.get("max_count", 50))
        else:
            result = f"未知工具: {tool_name}"

        return {"result": result}

    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"缺少必要参数: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"错误: {str(e)}")


@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "ok"}


def start_mcp_server():
    """启动 MCP HTTP Server"""
    global _server_instance
    mcp_host, mcp_port = get_mcp_config()
    _server_instance = uvicorn.Server(
        config=uvicorn.Config(
            app,
            host=mcp_host,
            port=mcp_port,
            log_level="warning",
        )
    )
    _server_instance.run()


def is_mcp_running() -> bool:
    """检查 MCP Server 是否正在运行"""
    import socket
    mcp_host, mcp_port = get_mcp_config()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    try:
        result = sock.connect_ex((mcp_host, mcp_port))
        return result == 0
    except Exception:
        return False
    finally:
        sock.close()


def ensure_mcp_started():
    """确保 MCP Server 已启动（如果尚未运行）"""
    if not is_mcp_running():
        print("🔄 启动 MCP Server...")
        # 在后台线程中启动
        import threading
        thread = threading.Thread(target=start_mcp_server, daemon=True)
        thread.start()
        # 等待服务器启动
        import time
        for _ in range(50):  # 最多等待 5 秒
            time.sleep(0.1)
            if is_mcp_running():
                break


async def main():
    """主函数 - 独立运行 MCP Server"""
    mcp_host, mcp_port = get_mcp_config()
    print("🚀 启动 EvolveRFC MCP Server...")
    print(f"📍 地址: http://{mcp_host}:{mcp_port}")
    print("📋 可用工具:")
    print("   - read: 读取文件内容")
    print("   - read_regex: 读取文件并用正则过滤")
    print("   - list: 列出目录文件")
    print("   - list_regex: 列出目录文件（正则过滤）")
    print("   - find: 递归查找文件")
    print("   - find_regex: 递归查找文件（正则过滤）")
    print("\nAPI 端点:")
    print(f"   GET  http://{mcp_host}:{mcp_port}/mcp/tools  - 列出工具")
    print(f"   POST http://{mcp_host}:{mcp_port}/mcp/call  - 调用工具")
    print(f"   GET  http://{mcp_host}:{mcp_port}/health    - 健康检查")

    config = uvicorn.Config(app, host=mcp_host, port=mcp_port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
