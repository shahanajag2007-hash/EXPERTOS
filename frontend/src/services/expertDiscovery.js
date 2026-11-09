import { postJSON } from "./api";

export async function loadDiscovery(expert) {

    const data = await postJSON("/expert/discovery", {
        expert: expert.shortRole || expert.role
    });

    if (!Array.isArray(data.steps) || data.steps.length === 0) {
        throw new Error("No discovery questions are available for this expert.");
    }

    return data.steps;

}
