const AVALAI_API_KEY = process.env.AVALAI_API_KEY;
const AVALAI_BASE_URL =
  process.env.AVALAI_BASE_URL || "https://api.avalai.ir/v1";
const EMBEDDING_MODEL = process.env.EMBEDDING_MODEL;
const EMBEDDING_DIMENSIONS = parseInt(process.env.EMBEDDING_DIMENSIONS, 10);

/**
 * Embeddings client for AvalAI's OpenAI-compatible Embeddings API.
 */
export class AvalAIEmbeddings {
  /**
   * Generate an embedding for a given text.
   * @param {string} text - The text to embed.
   * @param {object} [options] - Optional request body overrides.
   * @returns {Promise<Array<number>>} The embedding vector.
   */
  async generateEmbedding(text, options = {}) {
    const payload = {
      input: text,
      model: EMBEDDING_MODEL,
      encoding_format: "float",
      ...(EMBEDDING_DIMENSIONS ? { dimensions: EMBEDDING_DIMENSIONS } : {}),
      ...options,
    };

    try {
      const response = await fetch(`${AVALAI_BASE_URL}/embeddings`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${AVALAI_API_KEY}`,
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const errorBody = await response.text();
        throw new Error(
          `AvalAI embeddings request failed with status ${response.status}: ${errorBody}`
        );
      }

      const data = await response.json();
      return data.data[0].embedding;
    } catch (error) {
      console.error("Error generating embedding:", error);
      throw error;
    }
  }
}
