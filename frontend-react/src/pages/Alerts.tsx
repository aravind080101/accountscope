import { Bell, CheckCheck } from "lucide-react";
import { post } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { Button } from "@/components/ui/button";
import { Empty, Skeleton } from "@/components/ui/misc";
import { AlertList } from "@/pages/Company";

export default function AlertsPage({ refresh, rev }: any) {
  const { data, reload } = useApi<any>("/api/alerts", [rev]);
  return (
    <div className="flex h-full flex-col">
      <header className="flex h-14 shrink-0 items-center gap-3 border-b border-line px-6">
        <Bell className="size-4 text-muted" /><h1 className="text-[15px] font-semibold">Alerts</h1>
        {data?.unread ? <span className="text-[13px] text-saffron-ink">{data.unread} new</span> : null}
        <div className="ml-auto">{data?.unread ? <Button variant="outline" size="sm" onClick={async () => { await post("/api/alerts/read", {}); reload(); refresh(); }}><CheckCheck />Mark all as read</Button> : null}</div>
      </header>
      <div className="flex-1 bg-canvas p-6">
        <p className="mb-4 max-w-2xl text-[13px] text-muted">Watched accounts are re-checked every week while the app is running. New initiatives, stage changes, new leaders, hiring surges and new vendors land here.</p>
        {!data ? <Skeleton className="h-40 w-full" /> : data.alerts.length ? <AlertList alerts={data.alerts} withCompany /> : (
          <Empty icon={<Bell />} title="Nothing yet">Open an account and click Watch weekly. Changes will appear here after its next check.</Empty>
        )}
      </div>
    </div>
  );
}
