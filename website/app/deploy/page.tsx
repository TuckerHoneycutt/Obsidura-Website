import type { Metadata } from "next";
import { Chapter } from "@/components/chapter";
import { DeployBody } from "@/components/deploy";
import { chapterAt } from "@/lib/chapters";

const { chapter } = chapterAt("deploy");

export const metadata: Metadata = {
  title: chapter.title,
  description: chapter.description,
  alternates: { canonical: "/deploy" },
};

export default function DeployPage() {
  return (
    <Chapter slug="deploy">
      <DeployBody />
    </Chapter>
  );
}
