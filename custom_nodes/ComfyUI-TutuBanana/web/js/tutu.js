import { app } from "../../../scripts/app.js";

// Simplified Tutu Extension - AI nodes only
const TutuExtension = {
    name: "Tutu",
    
    async init() {
        console.log("[Tutu]", "Extension initialized - AI nodes only");
        // No UI elements - only AI nodes functionality
    },
    
    // No UI creation - removed all floating buttons and management features
};

app.registerExtension(TutuExtension);