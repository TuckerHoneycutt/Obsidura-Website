import type { Metadata } from "next";
import { Chapter } from "@/components/chapter";
import { AutomationsBody } from "@/components/automations";
import { RunWalkthrough } from "@/components/run-walkthrough";
import { ReportsBody } from "@/components/reports";
import { chapterAt } from "@/lib/chapters";

const { chapter } = chapterAt("automations");

export const metadata: Metadata = {
  title: chapter.title,
  description: chapter.description,
  alternates: { canonical: "/automations" },
};

export default function AutomationsPage() {
  return (
    <Chapter slug="automations">
      <AutomationsBody />
      {/* Having said what it runs, say how a run goes - then show one of the
          eight finishing, because the range is only credible if something is
          seen through to the end. */}
      <RunWalkthrough />
      <ReportsBody />
    </Chapter>
  );
}
