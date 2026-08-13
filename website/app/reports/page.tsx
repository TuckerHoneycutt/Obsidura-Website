import type { Metadata } from "next";
import { Chapter } from "@/components/chapter";
import { ReportsBody } from "@/components/reports";
import { chapterAt } from "@/lib/chapters";

const { chapter } = chapterAt("reports");

export const metadata: Metadata = {
  title: chapter.title,
  description: chapter.description,
  alternates: { canonical: "/reports" },
};

export default function ReportsPage() {
  return (
    <Chapter slug="reports">
      <ReportsBody />
    </Chapter>
  );
}
