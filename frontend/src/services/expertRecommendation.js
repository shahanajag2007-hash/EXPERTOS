import { postJSON } from "./api";

// fileIds: uploaded files the expert should read. conversationId: revise an
// existing Expert Room conversation instead of starting a new one.
export async function getRecommendation(expert, answers, { fileIds = [], conversationId = null } = {}) {

    return postJSON("/expert/recommend", {
        expert,
        answers,
        file_ids: fileIds,
        ...(conversationId ? { conversation_id: conversationId } : {}),
    });

}

// Suggest a starting expert for a free-text problem (AI Guide).
export async function matchExpert(problem) {

    return postJSON("/expert/match", { problem });

}
