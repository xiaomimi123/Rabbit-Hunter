import { Aperture } from './Aperture';

interface Props {
  /** legacy: number of placeholder rows (V1) — ignored in V2, kept for back-compat */
  rows?: number;
  message?: string;
  className?: string;
}

export function LoadingSkeleton({ message = '加载中…', className = '' }: Props) {
  return (
    <div className={`flex flex-col items-center justify-center py-14 text-ivory-40 ${className}`}>
      <Aperture size={42} rotate className="text-ivory-25 mb-3" />
      <div className="font-body italic text-[0.85rem]">{message}</div>
    </div>
  );
}
