import type { Metadata } from "next";
import { Chapter } from "@/components/chapter";
import { WorkflowsBody } from "@/components/definition";
import { chapterAt } from "@/lib/chapters";

const { chapter } = chapterAt("workflows");

export const metadata: Metadata = {
  title: chapter.title,
  description: chapter.description,
  alternates: { canonical: "/workflows" },
};

export default function WorkflowsPage() {
  return (
    <Chapter slug="workflows">
      <WorkflowsBody />
    </Chapter>
  );
}
