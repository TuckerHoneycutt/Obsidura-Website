import type { Metadata } from "next";
import { Chapter } from "@/components/chapter";
import { GovernanceBody } from "@/components/governance";
import { chapterAt } from "@/lib/chapters";

const { chapter } = chapterAt("governance");

export const metadata: Metadata = {
  title: chapter.title,
  description: chapter.description,
  alternates: { canonical: "/governance" },
};

export default function GovernancePage() {
  return (
    <Chapter slug="governance">
      <GovernanceBody />
    </Chapter>
  );
}
