import { z } from "zod"

export const PlatformError = z.object({ "code": z.enum(["AUTH_REQUIRED","BROKER_CONNECTION_REQUIRED","ENTITLEMENT_REQUIRED","DATA_STALE","PROVIDER_DEGRADED","RATE_LIMITED","INVALID_SYMBOL","MARKET_CLOSED","JOB_QUEUED","JOB_BUDGET_EXCEEDED","POLICY_DENIED","APPROVAL_REQUIRED","ORDER_STATE_CONFLICT","DUPLICATE_IDEMPOTENCY_KEY"]), "message": z.string(), "recovery_action": z.string(), "details": z.record(z.any()).default({}) }).strict()
