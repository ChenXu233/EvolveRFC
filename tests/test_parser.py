"""解析器单元测试
"""

import pytest

from evolve_rfc.utils.parser import (
    parse_agent_output,
    parse_clerk_output,
)


class TestParseAgentOutput:
    """parse_agent_output 测试类"""

    def test_parse_valid_output(self):
        """测试解析有效输出"""
        output = """论点: "该RFC设计合理"
论据: ["遵循SOLID原则", "扩展性良好"]
针对议题: "整体架构"
立场: 赞成
置信度: 0.8
"""
        result = parse_agent_output(output)

        assert result is not None
        assert result["论点"] == "该RFC设计合理"
        assert result["立场"] == "赞成"
        assert result["置信度"] == 0.8

    def test_parse_invalid_output(self):
        """测试解析无效输出"""
        output = "这是一段普通的文本输出，没有结构化格式"
        result = parse_agent_output(output)
        assert result is None

    def test_parse_empty_arguments(self):
        """测试解析空论据"""
        output = """论点: "测试"
论据: []
针对议题: "测试"
立场: "弃权"
置信度: 0.5
"""
        result = parse_agent_output(output)
        assert result is not None
        assert result["论据"] == []


class TestParseClerkOutput:
    """parse_clerk_output 测试类"""

    def test_parse_consensus_points(self):
        """测试解析共识点"""
        output = """## 共识点
- 议题1已解决
- 议题2达成一致

## 分歧点
- 议题3仍有争议

## 下一轮焦点
- 议题3
"""
        result = parse_clerk_output(output)

        assert "议题1已解决" in result["consensus_points"]
        assert "议题3仍有争议" in result["open_issues"]
        assert "议题3" in result["next_focus"]

    def test_parse_empty_sections(self):
        """测试解析空章节"""
        output = "这是一段没有结构化章节的文本"
        result = parse_clerk_output(output)

        assert result["consensus_points"] == []
        assert result["open_issues"] == []
        assert result["next_focus"] == []
