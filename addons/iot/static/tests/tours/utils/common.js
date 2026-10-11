export function waitForIotRequest(delay = 1000) {
    return {
        trigger: "body",
        run: async () => {
            await new Promise((resolve) => setTimeout(resolve, delay));
        },
    };
}
