import { InfiniteMarquee } from "@/components/ui/infinite-marquee";

const INTEGRATIONS = [
  "Postgres",
  "Salesforce",
  "Slack",
  "Stripe",
  "AWS",
  "Snowflake",
  "Zendesk",
  "NetSuite",
  "Kafka",
  "GitHub",
  "Jira",
  "Workday",
];

export function Integrations() {
  return (
    <section className="border-t border-rule">
      <div className="mx-auto flex max-w-6xl flex-col gap-5 px-5 py-10 sm:flex-row sm:items-center sm:gap-10">
        <p className="kicker shrink-0">hermes - carries word to</p>
        <InfiniteMarquee items={INTEGRATIONS} className="flex-1" />
      </div>
    </section>
  );
}
