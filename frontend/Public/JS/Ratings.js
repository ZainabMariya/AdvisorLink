// This script should be included in your Student.ejs view or in a separate JS file
document.addEventListener('DOMContentLoaded', function() {
    // Open rating modal when "Rate this course" button is clicked
    const rateButtons = document.querySelectorAll('.rate-course-btn');
    rateButtons.forEach(button => {
        button.addEventListener('click', function() {
            const courseId = this.getAttribute('data-course-id');
            document.getElementById(`rating-modal-${courseId}`).classList.add('show');
        });
    });
    
    // Close modal when "Back" is clicked
    const backButtons = document.querySelectorAll('.back-btn');
    backButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            const modal = this.closest('.rating-modal');
            // Add null check before accessing classList property
            if (modal) {
                modal.classList.remove('show');
            }
        });
    });
    
    // Handle star ratings
    const stars = document.querySelectorAll('.star');
    stars.forEach(star => {
        star.addEventListener('click', function() {
            const value = parseInt(this.getAttribute('data-value'));
            const courseId = this.getAttribute('data-course');
            const starsContainer = this.parentElement;
            const allStars = starsContainer.querySelectorAll('.star');
            
            // Update visual state
            allStars.forEach((s, index) => {
                if (index < value) {
                    s.classList.add('active');
                } else {
                    s.classList.remove('active');
                }
            });
            
            // Update rating text based on value
            let ratingText = '';
            switch(value) {
                case 1: ratingText = 'Extremely Easy'; break;
                case 2: ratingText = 'Easy'; break;
                case 3: ratingText = 'Met expectations'; break;
                case 4: ratingText = 'Difficult'; break;
                case 5: ratingText = 'Extremely Difficult'; break;
            }
            document.getElementById(`rating-text-${courseId}`).textContent = ratingText;
            
            // Store value for submission
            starsContainer.setAttribute('data-rating', value);
        });
    });
    
    // Handle form submission
    const saveButtons = document.querySelectorAll('.save-btn');
    saveButtons.forEach(button => {
        button.addEventListener('click', function() {
            const courseId = this.getAttribute('data-course-id');
            const modal = document.getElementById(`rating-modal-${courseId}`);
            
            if (!modal) {
                console.error(`Modal with ID rating-modal-${courseId} not found`);
                return;
            }
            
            const starsContainer = modal.querySelector('.star-rating');
            if (!starsContainer) {
                console.error('Star rating container not found');
                return;
            }
            
            const rating = starsContainer.getAttribute('data-rating');
            const feedbackElement = modal.querySelector('textarea');
            
            if (!feedbackElement) {
                console.error('Feedback textarea not found');
                return;
            }
            
            const feedback = feedbackElement.value;
            
            if (!rating) {
                alert('Please select a star rating');
                return;
            }

            // Show loading state
            this.textContent = 'Saving...';
            this.disabled = true;
            
            // Submit the rating (using fetch API)
            fetch(`/courses/${courseId}/rate`, {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    // Add CSRF token if you're using it
                    // 'X-CSRF-Token': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
                },
                body: JSON.stringify({
                    rating: parseInt(rating),
                    feedback: feedback
                })
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error('Network response was not ok');
                }
                return response.json();
            })
            .then(data => {
                console.log('Success:', data);
                modal.classList.remove('show');
                
                // Update the UI to reflect the new rating
                const courseItemElement = document.querySelector(`.course-item strong[data-course-id="${courseId}"]`);
                
                if (!courseItemElement) {
                    console.error(`Course item with ID ${courseId} not found`);
                    alert('Thank you for your rating!');
                    setTimeout(() => { location.reload(); }, 1000);
                    return;
                }
                
                const courseItem = courseItemElement.closest('.course-item');
                
                if (!courseItem) {
                    console.error('Parent course item not found');
                    alert('Thank you for your rating!');
                    setTimeout(() => { location.reload(); }, 1000);
                    return;
                }
                
                const ratingContainer = courseItem.querySelector('.rating-container');
                
                if (!ratingContainer) {
                    console.error('Rating container not found');
                    alert('Thank you for your rating!');
                    setTimeout(() => { location.reload(); }, 1000);
                    return;
                }
                
                // Check if there's already an average rating display
                let avgDisplay = courseItem.querySelector('.avg-rating');
                if (!avgDisplay) {
                    // If not, create one
                    avgDisplay = document.createElement('div');
                    avgDisplay.className = 'avg-rating';
                    ratingContainer.appendChild(avgDisplay);
                }
                
                // Update the star display to show user's rating
                const starElements = courseItem.querySelectorAll('.star');
                starElements.forEach((star, index) => {
                    if (index < parseInt(rating)) {
                        star.classList.add('active');
                    } else {
                        star.classList.remove('active');
                    }
                });
                
                // Refresh the page after a short delay to show updated ratings
                setTimeout(() => {
                    location.reload();
                }, 1000);
                
                // Show success message
                alert('Thank you for your rating!');
            })
            .catch((error) => {
                console.error('Error:', error);
                alert('Error submitting rating. Please try again.');
            })
            .finally(() => {
                // Reset button state
                this.textContent = 'Save and Continue';
                this.disabled = false;
            });
        });
    });
});