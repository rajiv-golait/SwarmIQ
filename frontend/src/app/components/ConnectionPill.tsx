interface ConnectionPillProps {
  isConnected: boolean;
}

export function ConnectionPill({ isConnected }: ConnectionPillProps) {
  return (
    <div className="flex items-center gap-2 text-sm mb-6">
      <div
        className={`w-2 h-2 rounded-full ${
          isConnected ? 'bg-[#22c55e]' : 'bg-[#ef4444]'
        }`}
      />
      <span className="text-[#98a2b4]">
        {isConnected ? 'Connected' : 'Backend offline'}
      </span>
    </div>
  );
}
