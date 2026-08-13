"""MyKnowledge backend package.

启动即拦截：h11 共享冲突版本断言。放在包最顶层，保证所有入口
（serve / MCP / CLI / 测试）import backend.* 时都会触发。
"""


def _assert_h11_compatible() -> None:
    """h11 与 httpcore 版本兼容性检查（生产路径保护）。

    httpx(mcp 依赖)→httpcore 要求 h11<0.15；httpx2(测试层)要求 h11>=0.16。
    生产路径只用 httpx，故 h11>=0.15 视为不兼容，拒绝启动——让"请求时诡异失败"
    提前暴露为"启动时清晰报错"。详见 KB「依赖升级检查清单.md」第六节。
    """
    try:
        import h11
    except ImportError:
        return  # h11 未安装（理论不出现），不拦截
    # 版本比较用打包后的元组，避免字符串比较坑（"0.15" < "0.9" 之类）
    from importlib.metadata import version as _ver
    try:
        v = tuple(int(x) for x in _ver("h11").split(".")[:2])
    except Exception:
        return  # 版本号解析失败则不拦截（宁松勿误伤）
    if v >= (0, 15):
        raise RuntimeError(
            f"h11 {'.'.join(map(str, v))} 与 httpcore 不兼容（要求 <0.15）。"
            f"请降级：pip install 'h11<0.15'。"
            f"详见 KB：依赖升级检查清单.md 第六节。"
        )


_assert_h11_compatible()
