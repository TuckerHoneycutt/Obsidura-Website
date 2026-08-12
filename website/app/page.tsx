import { Hero } from "@/components/hero";
import { AgentRun } from "@/components/agent-run";
import { SectionRail } from "@/components/section-rail";
import { Integrations } from "@/components/integrations";
import {
  FeatureSection,
  type FeatureContent,
} from "@/components/feature-section";
import { Deploy } from "@/components/deploy";
import { Interlude } from "@/components/interlude";
import { HEPHAESTUS } from "@/lib/engravings/hephaestus";

// Herakles and the Nemean Lion, first labor: the toil that forges the hide.
// Rendered from a black-figure engraving of the scene.
const HERAKLES = `                                                                    .
                                                             .+*@@@@@@#%#:
                                                            ;@@@@@@@@@@@@@@#        ;#%;
                                                           #@@@@@@@@@@@@@@@@#       @@@@@@@%: +%*:    ..
                                                           @@@@@@@@@@@@@@@@#+      *@@@@@@@@@@@#@@@@#@@@@@*;:
                                                          ;@@@@@#@#@@@@@#*@+       :@@@@@@@@@@#+#@@@@@@@@@@@@@*
                                                          *@@@@@@#@@@@@@@#@;       :%@;%@@@@@@@@@@@@@@@@@@@##@@@#;
                                                      .   +@@@@@@#@@@@@@@@@*            :@#@@@@@@@@@@@@@@@@@@*@@@@#;
                                                  %@@@@@@@@@@@@@@#@@@@@@@%               #@*@@@@@@@@@@@@@@@@@#@@@@*
                                                *@@@@@@@@@@@#@@@@@@@@@@@@%        ;..    @@*@@@@@@@@@@@@@@#@@@@@@@@@%
                                               +@@@@@@@@@@@@@##@@@@##@@@@@;       @##..+@@#@@@@@@@@@@@@@@@@@@@@#@@@@#*
                                               @@@@@@@@@@@@@@@%%@@@@@@@@@@@+     #@@@@@@@@@@@@@##@@@@@@@@@@%@@@@#@@@%
                                               @@@@@@@@@@@@@@@@@@@###@@@@@@@@%#%*%#@@#*@@@@#@@@@@@@%@@@#@@@#@@@@##@@@@:
                                               @@@@@@@@@@@@@@@@@@@@@@##@@@@@@@@@@@@#*;###@%@@@@@@@@%@@@#@@@@@@@@#@@@#*#
                                              ;@@@@@@@@@@@@@@@@@@@@@@@#%@%#@@@@@@@@##@@@@@@@@@@@@@@%@@#@@@@##@@@@@@@@%
                                              +@@@@@@@@#@@@@@@@@@@@@@@@@#@@@@@@@@@@@@@@@@@@@@@@@@@@+@@#@@@@#@@@#@%@@@@#
                                               @@@@@@@@@##@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@#@@@@@@##@@@@@##@@@@#@@@@;%:
                                               %@@@@@@@@@@##@@@@@@@@@@@@@@@@@@@@@@@@@@@##@@@@@@#@@@@@@@@%#@@@@@@#@@@@#
                                                #@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@%@@@@@@@@@@@@@%@@@@@#@@@@%#@@@@@@%
                                                :@@@@@@@@@@@@@@@@@@@@@@@%+*%%*+:#@@@#@@@@%@@@%%@@@@@@@@@@@@@@@@%@@@@# :                  :;+;:
                                                :@@@@@@@@@@@@@%##@@@@@%        :##@@@#@@@*%@@@@@@@@@@@@@@@@@@@@@@@#@@+               .#@@@@@@@@@*
                                                 @@@@@@@@@@@@@#@@@@@@@#          @@@@@@##@@@@@@@@@@@@@@@@@@@@@@@@@@  :              #@@*       +@@*
                                                ;@@@@@@@@@@@###@@@@@@@@@:       +@*@@@*#@@@@@@@@@@@@@@@@@@@@@@@@@@@;               @@@          ;@@@%:
                                              #@@@@@@@@@@@@@@#%@@@@@@@@@@@@%+;. . ;@@##@@@@@@@@@@@@@@@@@@@@@@@@@@@@#              +@@.          :@@@@@@:
                                             +@@@@@@@@@@@@@@@##@@@@@@@@@@@@@@@@@@@@@@+@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@+             *@@.           @@@@@@@*
                                           *@@@@@@@@@@@@@@@@@@@@@+  .+@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@            .@@#            @@@@@@@:
                                       :*#@@@@@@@@@@@@@@@@@@@@@@@@.     :%@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@*           +@@#            ;@@@@@@%.
                                      *@@@@@@@@@@@@@@@@@@@@@@@@@@@         :#@@@@@@@@@@@@@@@@@@@##@@@@@@@@@@@@@@@@@@@@@@@+          :@@@+             :**%#%:
                                      @@@@@@@@@@@@@@@@@@@@@@@@@@@@@.          *@@@@@@@@@@@@@@@#@@@@@@@@@@@@@@@@@@@@@@@@@@@@*          +@@@#:
                                     ;@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@#;         .+#@@@@@@@@@##@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@#:         :#@@@@*.
                                   :#@@@@@@@@@@@@@@@@@@@@@#@@@@@#@@@@@@@#.           .#@@@@..@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@%.         :%@@@@%:
                                 +@@@@@@@@@@@@@@@@@@@@@@#@@@@@@@@@@@@@@@@@*             ..    ;@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@*           +@@@@+
                               :@@@@@@@@@@@@@@@@@@@@@@@@@@#@@@@%@@@@@@@@@@@@%                   .*@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@#            *@@@:
                              .@@@@%#@@@@@@@@@@@@@@@@@@@@#@@@@#@@@@##@@@@@@@@@*                     .+%@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@%            @@@+
                                   @@@@@@@#@@@@@@@@@@@@#@@@@@@@@@#@@@@@@@@@@@@@@                          .;#@@@@@@@@@@@@@@@@@@@@@@@@@@@@            @@@:
                                  @@@@@@@@@@#@@@@@@@@@%#@@@@@@@@@@@@@@@@@@@@@@@@@:                           .####@@@@@#@@@@@@@@@@@@@@@@@@#.         ;@@#
                                 *@@@@@@@@@@@@@@%#@@@@@@@@@@+ :@@@@@@@@@@@@@@@@@@@.                          ;@@@@###@@#@@@@@@@@@@@@@@@@@@@@%        %@@#
                                 @@@@@@@@@@@@@@+    .:;;:.       +#@@@@@@@@@@@@@@@@@.                     :#@@@@@@@@@##@%@@@@@@@@@@@@@@@@@%@@@#;   .%@@@.
                                @@@@@@@@@@@@@#                       :+#@@@@@@@@@@@@@                   *@@@@@@@@@@@@@@%;@@@@@@@@@@@@@@@@@@.*@@@@@@@@@@:
                              .@@@@@@@@@@@@@+                             ;#@@@@@@@@@                 :@@@@@@@@@@@@@@@@@*#@@@@@@@@@@@@@@@@@.  .+%###*:
                           :*@@@@@@@@@@@@@*                                 @@@@@@@@%                .@@@@@@@@@@@@@@@@@@@+@@@@@@@@@@@@@@@@@:
                        +@@@@@@@@@@@@@@%;                                  #@@@@@@@@@                *@@@@@@@@@@@@@@@@@@@%@@@@@@@@@@@@@@@@@
                      *@@@@@@@@@@@@@@:                                     @@@@@@@@@@+                @@@@@@@@@@@@@@@@@@%..@@@@@@@@@@@@@@@@
                     @@@@@@@@@@@@#*:                                       @@@@@@@@@@@                 @@@@@@@@@@@@*:.     :@@@@@@@@@@@@@@@
                    %@@@@@@@@@@@.                                          @@@@@@@@@@@                  *@@@@@@@@@*         .@@@@@@@@@@@@@@@;
                    @@@@@@@@@@#                                            .@@@@@@@@@@.                   *@@@@@@@@;          :@@@@@@@@@@@@@@@%;.
                   @@@@@@@@@#:                                               #@@@@@@@@;                     #@@@@@@@@:           +#@@@@@@@@@@@@@@@@@@.
                  @@@@@@@@+                                                   .@@@@@@@+                     +@@@@@@@@@              .+%@@@@@@@@@@@@@@@
                 @@@@@@@:                                                      +@@@@@@%                    +@@@@@@@@%                      .:+#@@@@@@@+
                @@@@@@+                                                         #@@@@@@                  .@@@@@@@%.                             *@@@@@@.
               @@@@@@                                                            @@@@@@            ;;. :#@@@@@@+                                 .@@@@@@
            .#@@@@@@:                                                            #@@@@@%         +@@@@@@@@@@@+                                     @@@@@@
            @@@@@@@@+                                                            *@#@@@@%.      %@@@#@@@@@@@                                       ;@@@@@#
             #@@@@@@@                                                            @@@@@@@@@@*     :;.#+#* ..                                     **+#@@@@@@;
              %@@@@@@@                                                          :@@@@@@@@@@@@@+:.                                              @@@@@@@@@@%
               @@@@@@@@+                                                         #@@@#%*%#@@@@@@@@@;                                          %*%@@#@@@@#
                ;@@@@@@@@#                                                                       ..                                             :: :* ;.`;

const PLATFORM: FeatureContent = {
  id: "platform",
  kicker: "ii - pantheon, the labors",
  headlineLead: "Twelve labors?",
  headlineEmph: "Try twelve thousand.",
  lede:
    "Pantheon binds agents to your systems of record and hands them the toil, and a workflow only ascends to a human when it has to. Agents do the routine ninety percent; your team handles the judgment calls.",
  bullets: [
    "Agents reach your systems through resources - Postgres, object storage, and HTTP - and never hold a credential themselves.",
    "Workflows are authored as YAML and compiled into a typed graph. You write the references; the edges are derived, never drawn by hand.",
    "Every run is an append-only stream of events. Status, the audit trail, and recovery all read the same table, so none of them can drift.",
    "A task can gate on human approval. The pending decision persists, so a run survives a restart and continues when someone signs off.",
  ],
  closer: "Humans review exceptions, not everything.",
  art: HERAKLES,
  nerdLede:
    "Each workflow compiles to a typed graph before anything executes:",
  nerdBullets: [
    "Every task declares its input and output as a schema ref - name@version - so a mismatched pair is rejected at plan time, not at runtime.",
    "ptn plan diffs your definitions against the registry; ptn apply registers them. An invalid definition names the file, the field, and the rule it broke.",
    "Task bodies never receive credentials. The proxy checks the run's grants, makes the call with the real ones, and writes an audit event.",
    "An agent is an ordinary task carrying extra policy - same container, same protocol. Replacing one with deterministic code is a one-field change.",
  ],
};

const RUNTIME: FeatureContent = {
  id: "runtime",
  kicker: "iii - pantheon, the forge",
  headlineLead: "Automation shouldn't",
  headlineEmph: "feel fragile.",
  lede:
    "The reliability is forged in the runtime. We engineer the orchestration layer the way Hephaestus forged armor for the gods - like an operating system, not a chatbot - so agents keep working when models misbehave and upstreams slow down.",
  bullets: [
    "Every task carries a policy - timeout, retry, budget, idempotency - and runs in a container drawn from a warm pool, so cold starts never show.",
    "There are no checkpoints to fall out of sync. Executor state is a fold of the run's event log, so a killed executor rebuilds every run and finishes it.",
    "Structured outputs are schema-validated at every boundary; malformed responses are repaired or fail typed before they touch your data.",
    "Large data never travels inline. Files and tables move as handles, so a run costs the same whether it reasons over a hundred rows or fifty thousand.",
    "No agent framework is baked into the executor. The harness lives inside the runner image, and swapping it touches zero engine code.",
  ],
  closer: "The agents spend their time working, not failing quietly.",
  art: HEPHAESTUS,
  nerdLede:
    "The runtime treats model output as untrusted input, the same way a kernel treats userspace:",
  nerdBullets: [
    "Task bodies speak JSON-RPC over stdio from a warm container pool, and reach resources only through a Unix socket minted for that run.",
    "Events are appended before execution; recovery folds the log rather than re-running the model.",
    "When an agent's output fails its schema, a truncated error diff goes back to the model - two attempts, then a typed failure into the run log.",
    "Every value carries an envelope: producer, causing event, taint, and budget spent. Taint is recorded today, not yet enforced.",
  ],
  reverse: true,
};

export default function Home() {
  return (
    <>
      <SectionRail />
      <main>
        <Hero />
        <Integrations />
        <AgentRun />
        <FeatureSection content={PLATFORM} />
        <Interlude />
        <FeatureSection content={RUNTIME} />
        <Deploy />
      </main>
    </>
  );
}
