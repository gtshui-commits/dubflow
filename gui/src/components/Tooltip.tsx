import { CSSProperties, ReactNode, useState } from "react";

interface Props {
  /** 悬停或聚焦时显示的说明文字 */
  text: string;
  /** 出现方向，默认在元素上方 */
  side?: "top" | "bottom";
  /** 水平对齐；靠近右边缘的元素用 "right" 可避免提示溢出容器 */
  align?: "center" | "right";
  /** 附加到外层包裹元素的类名，例如 "grow" 让被包住的输入框继续撑满整行 */
  className?: string;
  /** 透传给外层包裹元素的内联样式（用于保持 flex 比例等布局） */
  style?: CSSProperties;
  children: ReactNode;
}

/**
 * 轻量悬停提示。
 *
 * 只用 CSS 定位，不引入 portal 或第三方库，所以可以直接包在任意按钮、
 * 下拉框、复选框外面。鼠标悬停和键盘聚焦（Tab）都会触发，保证可访问性。
 */
export default function Tooltip({
  text,
  side = "top",
  align = "center",
  className = "",
  style,
  children,
}: Props) {
  const [open, setOpen] = useState(false);
  return (
    <span
      className={`tip-wrap${className ? ` ${className}` : ""}`}
      style={style}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      {children}
      {open && (
        <span className={`tip-bubble tip-${side} tip-align-${align}`} role="tooltip">
          {text}
        </span>
      )}
    </span>
  );
}
