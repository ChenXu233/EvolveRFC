"""共享模块"""

from .debate import (
    run_parallel_review,
    run_review_with_viewpoint_pool,
    run_review_with_tools,  # 新增：多段思考评审
    analyze_votes,
    check_approval,
    build_viewpoint_pool_context,
    parse_viewpoints,
)

from .tools import (
    file_read,
    file_search,
    code_search,
    list_dir,
    get_all_tools,
    get_tool_names,
)

__all__ = [
    # 辩论函数
    "run_parallel_review",
    "run_review_with_viewpoint_pool",
    "run_review_with_tools",
    "analyze_votes",
    "check_approval",
    "build_viewpoint_pool_context",
    "parse_viewpoints",
    # 工具
    "file_read",
    "file_search",
    "code_search",
    "list_dir",
    "get_all_tools",
    "get_tool_names",
]
