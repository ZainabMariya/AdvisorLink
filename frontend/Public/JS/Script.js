document.addEventListener('DOMContentLoaded', function() {
    initChatbot();
    

    // Initialize GPA chart if on student page and element exists
    const gpaChartElement = document.getElementById('gpaChart');
    if (gpaChartElement) {
        initGPAChart();
    }

    // Initialize GPA chart using data from the page
    // Replace the existing initGPAChart function in your script.js
// Replace your existing initGPAChart function with this fixed version
function initGPAChart() {
    const ctx = document.getElementById('gpaChart').getContext('2d');
    if (!ctx) {
        console.error('GPA Chart canvas not found');
        return;
    }

    // Get the GPA data from the hidden element
    const gpaDataElement = document.getElementById('gpa-data');
    if (!gpaDataElement) {
        console.error('GPA data element not found');
        return;
    }
    
    // Debug log the raw content
    console.log('Raw GPA data content:', gpaDataElement.textContent);
    
     
    try {
        // Try to parse the data
        const parsedData = JSON.parse(gpaDataElement.textContent);
        console.log("Parsed GPA data:", parsedData);
        console.log("Data type:", typeof parsedData);
        console.log("Is array?", Array.isArray(parsedData));
        console.log("Length:", parsedData.length);
        
        if (parsedData.length > 0) {
            console.log("First record:", parsedData[0]);
            console.log("Sample semester:", parsedData[0].semester);
            console.log("Sample GPA:", parsedData[0].gpa);
        }
    } catch (e) {
        console.error("Error parsing GPA data:", e);
    }


    let gpaData = [];
    try {
        // Parse the JSON data
        gpaData = JSON.parse(gpaDataElement.textContent);
        console.log('Parsed GPA data:', gpaData);
        
        // Check if it's the expected format
        if (!Array.isArray(gpaData)) {
            console.error('GPA data is not an array:', gpaData);
            gpaData = [];
        }
    } catch (e) {
        console.error('Error parsing GPA data:', e);
    }
    
    // If no data found, use defaults
    if (gpaData.length === 0) {
        console.log('No GPA data found, using defaults');
        // Create sample data as fallback
        gpaData = [
            { semester: 'Fall 2023', gpa: 3.0 },
            { semester: 'Spring 2024', gpa: 3.2 }
        ];
    }
    
    // Sort the data by semester
    gpaData.sort((a, b) => {
        // Extract year and term from semester string
        const [termA, yearA] = (a.semester || '').split(' ');
        const [termB, yearB] = (b.semester || '').split(' ');
        
        // If we can't parse these properly, just use string comparison
        if (!yearA || !yearB) {
            return (a.semester || '').localeCompare(b.semester || '');
        }
        
        // Compare years first
        if (yearA !== yearB) {
            return parseInt(yearA) - parseInt(yearB);
        }
        
        // If years are the same, compare terms
        const termOrder = { 'Fall': 1, 'Spring': 2, 'Summer': 3 };
        return (termOrder[termA] || 0) - (termOrder[termB] || 0);
    });
    
    // Extract the labels and data from the sorted data
    const labels = gpaData.map(item => item.semester);
    const dataPoints = gpaData.map(item => {
        // Ensure GPA is a number
        const gpa = typeof item.gpa === 'number' ? item.gpa : parseFloat(item.gpa);
        return isNaN(gpa) ? 0 : gpa;
    });
    
    console.log('Chart Labels:', labels);
    console.log('Chart Data Points:', dataPoints);
    
    // Create the chart
    new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'GPA',
                data: dataPoints,
                borderColor: '#3498db',
                backgroundColor: 'rgba(52, 152, 219, 0.1)',
                tension: 0.4,
                fill: true
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: false,
                    min: 0.0,
                    max: 4.0
                }
            }
        }
    });
}
    
    // Chatbot functionality
    function initChatbot() {
        const chatbotToggle = document.getElementById('chatbotToggle');
        const chatbotContainer = document.getElementById('chatbotContainer');
        const chatbotClose = document.getElementById('chatbotClose');
        const chatbotMessages = document.getElementById('chatbotMessages');
        const chatbotInput = document.getElementById('chatbotInput');
        const chatbotSend = document.getElementById('chatbotSend');
        const chatbotMaximize = document.getElementById('chatbotMaximize');
        const chatbotMinimize = document.getElementById('chatbotMinimize');
        
        // Skip if elements not found (not on a page with chatbot)
        if (!chatbotToggle || !chatbotContainer) return;
        
        let isMaximized = false;
        let isMinimized = false;
        
        // Toggle chatbot visibility
        chatbotToggle.addEventListener('click', () => {
            if (chatbotContainer.style.display === 'flex') {
                chatbotContainer.style.display = 'none';
            } else {
                chatbotContainer.style.display = 'flex';
                // Reset to normal size when opening
                resetChatbotSize();
            }
        });
        
        // Close chatbot
        chatbotClose.addEventListener('click', () => {
            chatbotContainer.style.display = 'none';
        });
        
        // Maximize chatbot
        chatbotMaximize.addEventListener('click', () => {
            if (isMaximized) {
                resetChatbotSize();
            } else {
                chatbotContainer.classList.add('maximized');
                chatbotContainer.classList.remove('minimized');
                isMaximized = true;
                isMinimized = false;
                chatbotMaximize.textContent = '□'; // Change icon if you want
            }
        });
        
        // Minimize chatbot
        chatbotMinimize.addEventListener('click', () => {
            if (isMinimized) {
                resetChatbotSize();
            } else {
                chatbotContainer.classList.add('minimized');
                chatbotContainer.classList.remove('maximized');
                isMinimized = true;
                isMaximized = false;
                chatbotMinimize.textContent = '_'; // Change icon if you want
            }
        });
        
        // Reset to default size
        function resetChatbotSize() {
            chatbotContainer.classList.remove('maximized');
            chatbotContainer.classList.remove('minimized');
            isMaximized = false;
            isMinimized = false;
            chatbotMaximize.textContent = '□';
            chatbotMinimize.textContent = '_';
        }
        
        // Send message function
        function sendMessage() {
            const message = chatbotInput.value.trim();
            if (!message) return;

            // Add user message to the chat
            addMessage(message, 'user');
            chatbotInput.value = '';

            // Show typing indicator
            const typingIndicator = document.createElement('div');
            typingIndicator.classList.add('message', 'bot-message', 'typing');
            typingIndicator.textContent = 'Typing...';
            chatbotMessages.appendChild(typingIndicator);

            console.log('Sending message to backend:', message); // Debug log

            // Send the message to the Flask backend
            fetch(`${process.env.BACKEND_URL}/chatbot`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                mode: 'cors',
                credentials: 'include',
                body: JSON.stringify({ prompt: message, userType: window.USER_TYPE })
            })
            .then(async response => {
                console.log('Response status:', response.status); // Debug log
                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({}));
                    throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                // Remove typing indicator
                typingIndicator.remove();
                // Add the bot's response to the chat
                if (data.error) {
                    addMessage(`Error: ${data.error}`, 'bot');
                } else {
                    addMessage(data.answer, 'bot');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                // Remove typing indicator
                typingIndicator.remove();
                addMessage(`Sorry, there was an error: ${error.message}. Please check if the backend server is running.`, 'bot');
            });
        }
        
        // Attach sendMessage to the send button and input field
        chatbotSend.addEventListener('click', sendMessage);
        chatbotInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                sendMessage();
            }
        });
        
        // Add message to chat
        function addMessage(text, sender) {
            const messageElement = document.createElement('div');
            messageElement.classList.add('message');
            messageElement.classList.add(sender === 'user' ? 'user-message' : 'bot-message');
            messageElement.textContent = text;
            chatbotMessages.appendChild(messageElement);
            chatbotMessages.scrollTop = chatbotMessages.scrollHeight;
        }
    }
});