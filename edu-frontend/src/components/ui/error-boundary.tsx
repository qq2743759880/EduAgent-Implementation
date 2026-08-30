"use client";

/**
 * ErrorBoundary — 全局错误边界（Phase 4 用户体验）
 *
 * 作用：
 * - 捕获子组件渲染错误，避免整个页面白屏
 * - 显示友好的错误提示 + 重试按钮
 * - 面试考点：React 错误边界的实现原理（getDerivedStateFromError/componentDidCatch）
 *
 * 对标作业帮/猿辅导：
 * - 生产环境不暴露错误堆栈（安全）
 * - 提供"刷新页面"和"重试"两个恢复路径
 * - 开发环境保留错误详情方便排查
 */
import { Component, type ReactNode } from "react";

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    // 更新 state 使下一次渲染显示降级 UI
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    // 生产环境应上报到 Sentry 等监控平台
    console.error("[ErrorBoundary] 捕获到渲染错误:", error, errorInfo);
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
  };

  handleRefresh = () => {
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      // 默认降级 UI
      return (
        <div className="flex min-h-screen items-center justify-center bg-gray-50 p-8">
          <div className="max-w-md text-center">
            {/* 错误图标 */}
            <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-red-100">
              <svg
                className="h-8 w-8 text-red-500"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"
                />
              </svg>
            </div>

            <h2 className="mb-2 text-xl font-semibold text-gray-900">
              页面出现异常
            </h2>
            <p className="mb-2 text-sm text-gray-500">
              很抱歉，页面渲染时遇到了错误。请尝试刷新页面或重试。
            </p>

            {/* 开发环境显示错误详情 */}
            {process.env.NODE_ENV !== "production" && this.state.error && (
              <details className="mb-4 text-left">
                <summary className="cursor-pointer text-xs text-gray-400 hover:text-gray-600">
                  查看错误详情
                </summary>
                <pre className="mt-2 max-h-40 overflow-auto rounded bg-gray-100 p-2 text-xs text-red-600">
                  {this.state.error.message}
                  {"\n"}
                  {this.state.error.stack}
                </pre>
              </details>
            )}

            {/* 操作按钮 */}
            <div className="flex justify-center gap-3">
              <button
                onClick={this.handleRetry}
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
              >
                重试
              </button>
              <button
                onClick={this.handleRefresh}
                className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
              >
                刷新页面
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}