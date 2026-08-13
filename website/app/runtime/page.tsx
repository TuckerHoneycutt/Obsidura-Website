import type { Metadata } from "next";
import { Chapter } from "@/components/chapter";
import { RuntimeBody } from "@/components/runtime";
import { chapterAt } from "@/lib/chapters";

const { chapter } = chapterAt("runtime");

export const metadata: Metadata = {
  title: chapter.title,
  description: chapter.description,
  alternates: { canonical: "/runtime" },
};

export default function RuntimePage() {
  return (
    <Chapter slug="runtime">
      <RuntimeBody />
    </Chapter>
  );
}
