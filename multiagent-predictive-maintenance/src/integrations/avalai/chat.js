import { ChatOpenAI } from "@langchain/openai";

const AVALAI_API_KEY = process.env.AVALAI_API_KEY;
const AVALAI_BASE_URL =
  process.env.AVALAI_BASE_URL || "https://api.avalai.ir/v1";
const COMPLETION_MODEL = process.env.COMPLETION_MODEL;

let avalaiClient = null;

/**
 * Initialize a client for AvalAI's OpenAI-compatible Chat Completions API.
 * @returns {ChatOpenAI} Initialized chat client
 */
export function createChatClient() {
  if (!avalaiClient) {
    avalaiClient = new ChatOpenAI({
      model: COMPLETION_MODEL,
      apiKey: AVALAI_API_KEY,
      configuration: { baseURL: AVALAI_BASE_URL },
    });
  }
  return avalaiClient;
}

/**
 * Send messages to AvalAI and get a response
 * @param {Array} messages - Array of messages in LangChain format
 * @returns {Promise<Object>} - Response from the model
 */
export async function invokeChat(messages) {
  try {
    return await createChatClient().invoke(messages);
  } catch (error) {
    console.error("Error invoking AvalAI:", error);
    throw new Error(`AvalAI conversation failed: ${error.message}`);
  }
}

/**
 * Stream responses from AvalAI
 * @param {Array} messages - Array of messages in LangChain format
 * @returns {Promise<AsyncIterable>} - Stream of responses
 */
export async function streamChat(messages) {
  try {
    return await createChatClient().stream(messages);
  } catch (error) {
    console.error("Error streaming from AvalAI:", error);
    throw new Error(`AvalAI streaming failed: ${error.message}`);
  }
}
