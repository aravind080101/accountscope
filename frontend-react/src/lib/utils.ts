import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export const cn = (...inputs: ClassValue[]) => twMerge(clsx(inputs));
export const pct = (x?: number | null) => Math.round((x || 0) * 100);
export const initials = (n = "") => n.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
export const day = (s?: string | null) => (s ? s.slice(0, 10) : "");

export const STAGES: [string, string][] = [
  ["hinted", "Hinted"], ["announced", "Announced"], ["hiring", "Hiring"], ["in_flight", "In flight"], ["vendor_selection", "Choosing vendors"],
];
export const STAGE_LABEL = Object.fromEntries(STAGES);
export const SOURCE_LABEL: Record<string, string> = {
  jobs: "Job posts", news: "News", vendor: "Vendor news", filing: "Filings", blog: "Eng. blogs", tech: "Tech mentions",
  case_study: "Case studies", post: "Public posts", deal: "Deal news", footprint: "Location news", project: "Project news",
};
export const ALERT_LABEL: Record<string, string> = {
  new_initiative: "New initiative", new_project: "New project", stage_change: "Stage change", new_leader: "New leader", hiring_surge: "Hiring surge", new_vendor: "New vendor",
};
const PALETTE = ["#6d4aff", "#0e8a6a", "#b56d00", "#2563eb", "#c03a26", "#0f766e", "#7c3aed", "#9a3412"];
export const tint = (s = "") => PALETTE[[...s].reduce((a, c) => a + c.charCodeAt(0), 0) % PALETTE.length];
