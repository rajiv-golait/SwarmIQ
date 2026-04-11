interface EmptyStateProps {
  message: string;
}

export function EmptyState({ message }: EmptyStateProps) {
  return (
    <div className="flex items-center justify-center h-64 text-[#98a2b4]">
      {message}
    </div>
  );
}
