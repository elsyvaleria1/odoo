/** @odoo-module native */
const _FACEBOOK_REACTIONS = {
    LIKE: "👍",
    LOVE: "❤️",
    HAHA: "😆",
    WOW: "😮",
    SAD: "😥",
    ANGRY: "😡",
    CARE: "🥰",
};

export function formatFacebookReactions(reactions, limit) {
    let sorted = Object.entries(reactions || {})
        .filter(([, reactionCount]) => reactionCount !== 0)
        .sort(
            ([, reactionCount1], [, reactionCount2]) => reactionCount2 - reactionCount1,
        );

    if (limit) {
        sorted = sorted.slice(0, limit);
    }

    return sorted.map(([reactionName, reactionCount]) => [
        _FACEBOOK_REACTIONS[reactionName],
        reactionCount,
    ]);
}
