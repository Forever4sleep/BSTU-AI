import { useEffect, useState } from "react";

import { buildApiUrl } from "../api";
import { getStudentAccessToken } from "../studentAccessKey";

type Props = {
  fullName: string;
  hasAvatar: boolean;
  revision: number;
};

/** Аватары отдаются с Bearer — грузим в blob для <img>. */
export function StudentDashboardAvatar({ fullName, hasAvatar, revision }: Props) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!hasAvatar) {
      setBlobUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
      return;
    }

    const t = getStudentAccessToken().trim();
    if (!t) return;

    let dead = false;
    void (async () => {
      const r = await fetch(buildApiUrl("/api/public/me/avatar"), {
        headers: { Authorization: `Bearer ${t}` },
        cache: "no-store",
      });
      if (dead || !r.ok) return;
      const blob = await r.blob();
      if (dead) return;
      const next = URL.createObjectURL(blob);
      setBlobUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return next;
      });
    })();

    return () => {
      dead = true;
      setBlobUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
    };
  }, [hasAvatar, revision]);

  const initials = fullName
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("") || "?";

  return (
    <div className="stu-dash-avatar">
      {blobUrl ? (
        <img src={blobUrl} alt="" className="stu-dash-avatar__img" width={112} height={112} decoding="async" />
      ) : (
        <span className="stu-dash-avatar__fallback">{initials}</span>
      )}
    </div>
  );
}
