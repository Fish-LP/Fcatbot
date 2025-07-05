import functools
import warnings
# 设置默认的弃用警告过滤器
warnings.simplefilter('always', DeprecationWarning)

def deprecated(func=None, *, reason=None, version=None, force_error=False):
    """
    标记函数为已弃用的装饰器，支持强制抛出错误
    
    Args:
        reason: 弃用的原因或替代方案
        version: 弃用的版本
        force_error: 是否强制抛出错误（默认 False）
    
    使用示例:
        @deprecated(reason="请使用 new_function 替代。", version="1.0", force_error=False)
        def old_function():
            pass
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            warning_message = f"调用了已弃用的函数 {func.__name__}。"
            if version:
                warning_message += f" 该函数自版本 {version} 起已被弃用。"
            if reason:
                warning_message += f" {reason}"
            
            if force_error:
                raise DeprecationWarning(warning_message)
            else:
                warnings.warn(
                    warning_message,
                    category=DeprecationWarning,
                    stacklevel=2
                )
            
            return func(*args, **kwargs)
        
        # 添加弃用信息到文档字符串
        if wrapper.__doc__:
            deprecation_note = "\n\n.. deprecated:: "
            if version:
                deprecation_note += f"{version}"
            else:
                deprecation_note += "未知版本"
            
            if reason:
                deprecation_note += f"\n   {reason}"
            
            wrapper.__doc__ = deprecation_note + (wrapper.__doc__ or "")
        else:
            wrapper.__doc__ = f"\n\n.. deprecated:: 未知版本\n   {reason if reason else '未提供原因。'}"
        
        return wrapper
    
    if func is None:
        return decorator
    else:
        return decorator(func)