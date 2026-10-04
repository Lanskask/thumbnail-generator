// Bundle entry point. The Workers runtime rejects any named export that is not a handler or a
// class, so this file exports only the default handler; src/index.ts keeps the testable helpers.
import { handle, type Env } from "./index";

export default { fetch: handle } satisfies ExportedHandler<Env>;
