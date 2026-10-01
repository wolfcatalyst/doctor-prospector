interface BadgeProps {
  children: React.ReactNode;
  variant?: "gray" | "green" | "yellow" | "red" | "blue" | "purple" | "orange";
  size?: "sm" | "md";
}

const variants: Record<string, string> = {
  gray: "bg-gray-100 text-gray-700",
  green: "bg-green-100 text-green-700",
  yellow: "bg-yellow-100 text-yellow-700",
  red: "bg-red-100 text-red-700",
  blue: "bg-blue-100 text-blue-700",
  purple: "bg-purple-100 text-purple-700",
  orange: "bg-orange-100 text-orange-700",
};

export default function Badge({
  children,
  variant = "gray",
  size = "sm",
}: BadgeProps) {
  const sizeClasses =
    size === "sm" ? "px-2 py-0.5 text-xs" : "px-2.5 py-1 text-sm";
  return (
    <span
      className={`inline-flex items-center rounded-full font-medium ${variants[variant]} ${sizeClasses}`}
    >
      {children}
    </span>
  );
}
