import { beforeEach } from "vitest";
import { installVoiceMocks, resetVoiceMocks } from "./voiceMocks";

installVoiceMocks();

beforeEach(() => {
  resetVoiceMocks();
});
