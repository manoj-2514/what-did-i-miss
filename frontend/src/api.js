/**
 * API Integration Module for "What Did I Miss?"
 * Connects directly to local FastAPI + Ollama backend endpoint.
 * Supports ?mock=1 query parameter mode for offline hackathon demonstration.
 */

export const MOCK_ANALYSIS_DATA = {
  tldr: [
    "Hackathon prototype submission deadline is strictly 5:00 PM today.",
    "FastAPI wrapper deployed on port 8000 routing local Ollama llama3 model prompts.",
    "Manoj is assigned to finalize report and verify 0 outgoing cloud network requests."
  ],
  attention: [
    {
      sender: "Rahul",
      text: "Manoj, please submit the report by 5pm",
      reason: "mention",
      priority: "high"
    },
    {
      sender: "Rahul",
      text: "Which port is Ollama listening on? Currently defaulting to 11434.",
      reason: "question",
      priority: "medium"
    },
    {
      sender: "Priya",
      text: "Can someone confirm if the hackathon submission deck is due today by 5pm?",
      reason: "deadline",
      priority: "low"
    }
  ],
  decisions: [
    "The team agreed to lock codebase by 4pm and run completely offline Wi-Fi pitch demo.",
    "Architecture decision confirmed: 100% on-device local execution with zero cloud telemetry."
  ],
  action_items: [
    {
      task: "Submit the report",
      owner: "Manoj",
      deadline: "today by 5pm"
    },
    {
      task: "Verify 0 outgoing network requests via DevTools",
      owner: "Manoj",
      deadline: "before demo"
    },
    {
      task: "Test offline Wi-Fi disconnect pitch presentation",
      owner: "Dev Lead",
      deadline: "4:30 PM"
    }
  ],
  messages: [
    {
      sender: "Rahul",
      time: "10:15 AM",
      text: "Manoj, did you push the updated FastAPI endpoints to main?",
      priority: "medium",
      tags: ["question"]
    },
    {
      sender: "Manoj",
      time: "10:18 AM",
      text: "I am running local Ollama llama3 model tests now. Will push in 5 minutes!",
      priority: "low",
      tags: []
    },
    {
      sender: "Priya",
      time: "10:20 AM",
      text: "Can someone confirm if the hackathon submission deck is due today by 5pm?",
      priority: "medium",
      tags: ["deadline"]
    },
    {
      sender: "Rahul",
      time: "10:22 AM",
      text: "Manoj, please submit the report by 5pm as discussed in our sync meeting.",
      priority: "high",
      tags: ["mention", "deadline"]
    },
    {
      sender: "Manoj",
      time: "10:28 AM",
      text: "Confirmed, decision made to lock codebase by 4pm and run offline Wi-Fi pitch demo.",
      priority: "medium",
      tags: ["decision"]
    }
  ],
  stats: {
    total_messages: 5,
    participants: 3
  }
};

export const HARDCODED_DEMO_CHAT = `[10:15 AM] Rahul: Manoj, did you push the updated FastAPI endpoints to main?
[10:18 AM] Manoj: I am running local Ollama llama3 model tests now. Will push in 5 minutes!
[10:20 AM] Priya: Can someone confirm if the hackathon submission deck is due today by 5pm?
[10:22 AM] Rahul: Manoj, please submit the report by 5pm as discussed in our sync meeting.
[10:25 AM] Vikram: Pepperoni and veggie pizzas ordered for Room 302!
[10:28 AM] Manoj: Confirmed, decision made to lock codebase by 4pm and run offline Wi-Fi pitch demo.
[10:30 AM] Rahul: @Manoj Which port is Ollama listening on? Currently defaulting to 11434.`;

/**
 * Check if ?mock=1 URL query parameter is active.
 * @returns {boolean}
 */
export function isMockMode() {
  if (typeof window === 'undefined') return false;
  const params = new URLSearchParams(window.location.search);
  return params.get('mock') === '1';
}

/**
 * Send chat payload to backend for analysis, or return mock data if ?mock=1.
 * @param {string} userName 
 * @param {string} chatText 
 * @returns {Promise<Object>}
 */
export async function analyzeChat(userName, chatText) {
  // If ?mock=1 parameter is present, return instant local mock response
  if (isMockMode()) {
    await new Promise(resolve => setTimeout(resolve, 800)); // Simulate realistic delay
    const mockCopy = JSON.parse(JSON.stringify(MOCK_ANALYSIS_DATA));
    mockCopy.action_items[0].owner = userName || 'Manoj';
    return mockCopy;
  }

  try {
    const response = await fetch('/analyze', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        user_name: userName,
        chat: chatText,
      }),
    });

    if (!response.ok) {
      let errorDetail = '';
      try {
        const errorData = await response.json();
        errorDetail = errorData.detail || errorData.message || JSON.stringify(errorData);
      } catch (e) {
        errorDetail = await response.text();
      }

      if (response.status === 422) {
        throw new Error(`Validation Error (422): ${errorDetail || 'Invalid input submitted.'}`);
      }

      throw new Error(`Analysis failed (${response.status}): ${errorDetail || response.statusText}`);
    }

    return await response.json();
  } catch (error) {
    if (error.name === 'TypeError' && error.message.includes('fetch')) {
      throw new Error('LOCAL ENGINE UNAVAILABLE. Please check if FastAPI is running on http://localhost:8000, or append ?mock=1 to test offline.');
    }
    throw error;
  }
}

/**
 * Check backend health status via GET /health endpoint.
 * @returns {Promise<boolean>}
 */
export async function checkHealth() {
  if (isMockMode()) return true;
  try {
    const response = await fetch('/health', {
      method: 'GET',
      headers: { 'Accept': 'application/json' },
    });
    return response.ok;
  } catch (err) {
    return false;
  }
}

/**
 * Fetch sample chat from /sample_chats/demo.txt or fallback.
 * @returns {Promise<string>}
 */
export async function fetchSampleChat() {
  try {
    const response = await fetch('/sample_chats/demo.txt');
    if (response.ok) {
      const text = await response.text();
      if (text && text.trim().length > 0) {
        return text;
      }
    }
  } catch (err) {
    // Fallback if route fails
  }
  return HARDCODED_DEMO_CHAT;
}
