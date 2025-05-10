// controllers/courseRatingController.js
const CourseRating = require('../models/CourseRating');
const Course = require('../models/Course');
const { Op } = require('sequelize');

// Controller for handling course ratings
const courseRatingController = {
  
  // Rate a course (create or update rating)
  async rateAndReviewCourse(req, res) {
    try {
      const { courseId } = req.params;
      const { rating, feedback } = req.body;
      const studentId =  req.session.userId; // Assuming user info is in request
      
      if (!courseId || !rating) {
        return res.status(400).json({ 
          success: false, 
          message: 'Course ID and rating are required' 
        });
      }
      
      // Check if course exists
      const course = await Course.findByPk(courseId);
      if (!course) {
        return res.status(404).json({ 
          success: false, 
          message: 'Course not found' 
        });
      }
      
      // Check if rating already exists for this student and course
      const existingRating = await CourseRating.findOne({
        where: {
          student_id: studentId,
          course_id: courseId
        }
      });
      
      if (existingRating) {
        // Update existing rating
        existingRating.rating = rating;
        existingRating.feedback = feedback || existingRating.feedback;
        await existingRating.save();
        
        return res.status(200).json({
          success: true,
          message: 'Rating updated successfully',
          data: existingRating
        });
      } else {
        // Create new rating
        const newRating = await CourseRating.create({
          student_id: studentId,
          course_id: courseId,
          rating: rating,
          feedback: feedback || null
        });
        
        return res.status(201).json({
          success: true,
          message: 'Rating submitted successfully',
          data: newRating
        });
      }
    } catch (error) {
      console.error('Error in rateAndReviewCourse:', error);
      return res.status(500).json({
        success: false,
        message: 'Error processing rating',
        error: error.message
      });
    }
  },
  
  // Get average rating for a course
  async getAverageCourseRating(req, res) {
    try {
      const { courseId } = req.params;
      
      const ratings = await CourseRating.findAll({
        where: { course_id: courseId }
      });
      
      if (!ratings || ratings.length === 0) {
        return res.status(200).json({
          success: true,
          averageRating: 0,
          ratingCount: 0,
          message: 'No ratings found for this course'
        });
      }
      
      // Calculate average rating
      const sum = ratings.reduce((acc, rating) => acc + rating.rating, 0);
      const averageRating = (sum / ratings.length).toFixed(1);
      
      return res.status(200).json({
        success: true,
        averageRating: parseFloat(averageRating),
        ratingCount: ratings.length
      });
    } catch (error) {
      console.error('Error in getAverageCourseRating:', error);
      return res.status(500).json({
        success: false,
        message: 'Error retrieving course ratings',
        error: error.message
      });
    }
  },
  
  // Get a student's rating for a specific course
  async getStudentCourseRating(req, res) {
    try {
      const { courseId } = req.params;
      const studentId = req.user.student_id;
      
      const rating = await CourseRating.findOne({
        where: {
          student_id: studentId,
          course_id: courseId
        }
      });
      
      if (!rating) {
        return res.status(404).json({
          success: false,
          message: 'No rating found'
        });
      }
      
      return res.status(200).json({
        success: true,
        data: rating
      });
    } catch (error) {
      console.error('Error in getStudentCourseRating:', error);
      return res.status(500).json({
        success: false,
        message: 'Error retrieving rating',
        error: error.message
      });
    }
  }
};

module.exports = courseRatingController;