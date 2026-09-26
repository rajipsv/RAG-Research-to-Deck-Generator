import { Queue } from "bullmq";
import IORedis from "ioredis";

declare global {
  // eslint-disable-next-line no-var
  var __deckQueue: Queue | undefined;
  // eslint-disable-next-line no-var
  var __deckQueueConnection: IORedis | undefined;
}

// Next.js dev mode hot-reloads route modules; cache on globalThis so we don't
// open a fresh Redis connection on every request.
function getConnection(): IORedis {
  if (!globalThis.__deckQueueConnection) {
    globalThis.__deckQueueConnection = new IORedis(
      process.env.REDIS_URL || "redis://localhost:6379",
      { maxRetriesPerRequest: null }
    );
  }
  return globalThis.__deckQueueConnection;
}

export const QUEUE_NAME = "deck-generation";

export function getDeckQueue(): Queue {
  if (!globalThis.__deckQueue) {
    globalThis.__deckQueue = new Queue(QUEUE_NAME, { connection: getConnection() });
  }
  return globalThis.__deckQueue;
}

export type PipelineResult = {
  filename: string;
  paperCount: number;
  slideCount: number;
  downloadUrl: string;
};
