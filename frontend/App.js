const express = require('express');
const bodyParser = require('body-parser');
const session = require('express-session');
const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '../.env') }); // Load environment variables from root .env
const sequelize = require('./config/database.js');
require('./models/Department');
require('./models/Major');
const Student = require('./models/Student');
const Advisor = require('./models/Advisor');
const Course = require('./models/Course');
require('./models/StudentGPAHistory');
require('./models/HighRiskStudents')
const HighRiskStudentsModel = require('./models/HighRiskStudents');
const StudentCourseEnrollment = require('./models/StudentCourseEnrollment.js');
const StudentCourseAbsences = require('./models/StudentCourseAbsences');
const CourseRating = require('./models/CourseRating');
const courseRatingController = require('./controllers/courseRatingController');
const fetch = require('node-fetch');
const { exec } = require('child_process');
const fs = require('fs');

// then sync or authenticate as needed

const { Op } = require('sequelize'); // Import Sequelize operators
const app = express();
const bcrypt = require('bcrypt');
const cors = require('cors');

// Basic security middleware
app.use((req, res, next) => {
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('X-Frame-Options', 'DENY');
    next();
});

sequelize.authenticate()
    .then(() => {
        console.log('Connection has been established successfully.');
    })
    .catch(err => {
        console.error('Unable to connect to the database:', err.message);
    });



// Middleware setup
app.set('views', path.join(__dirname, 'views'));
app.set('view engine', 'ejs');

// Security and parsing middleware
app.use(cors({
    origin: true,
    credentials: true,
    methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
    allowedHeaders: ['Content-Type', 'Authorization', 'Cookie']
}));
app.use(express.json());
app.use(bodyParser.urlencoded({ extended: true }));

// Static file serving
app.use(express.static(path.join(__dirname, 'Public')));
app.use('/CSS', express.static(path.join(__dirname, 'Public/CSS')));
app.use('/JS', express.static(path.join(__dirname, 'Public/JS')));

// Add this near the top of your app.js, after requiring express
app.set('view engine', 'ejs');

// Session setup
app.use(
    session({
        secret: process.env.SESSION_SECRET,
        resave: false,
        saveUninitialized: false,
        cookie: {
            maxAge: 1000 * 60 * 60, // 1 hour session duration
            secure: process.env.NODE_ENV === 'production',
            httpOnly: true,
            sameSite: 'lax'
        },
    })
);

// Sync Sequelize models with the database
sequelize.sync({ alter: true })
    .then(() => {
        console.log('All models were synchronized successfully.');
    })
    .catch(err => {
        console.error('Error synchronizing models:', err.message);
    });




//default
 app.get('/', (req, res) => {
    res.render('login', { message: '' });
 });  
// Routes
app.post('/login', async (req, res) => {
    try {
        console.log('[Login] body →', req.body);
     
        const userType = req.body['user-type'];
        const { username, password } = req.body;
        console.log('[Login] payload:', { userType, username });
    
        const Model = userType === 'faculty' ? Advisor : Student;
        if (!Model) {
            throw new Error(`Unknown user-type: ${userType}`);
        }
    
        // Change this line to search by ID instead of email
        const user = await Model.findOne({ 
            where: userType === 'faculty' 
                ? { advisor_id: username } 
                : { student_id: username }
        });
        
        console.log('[Login] user found:', user ? 'Yes' : 'No');
        
        if (!user) {
            console.log('[Login] No user found with ID:', username);
            return res.render('login', { message: 'No such user.' });
        }

        console.log('[Login] Attempting password compare');
        // For testing only - replace with proper bcrypt check in production
        const match = password === user.password;
        console.log('[Login] Password match:', match ? 'Yes' : 'No');
        
        if (!match) {
            console.log('[Login] Password mismatch for user:', username);
            return res.render('login', { message: 'Wrong password.' });
        }

        req.session.userId = user.student_id || user.advisor_id;
        req.session.userType = userType;
        console.log('[Login] Session set, redirecting user');

        // Redirect based on user type
        if (userType === 'faculty') {
            return res.redirect(`/advisor/${user.advisor_id}`);
        } else {
            // For students, render the student page directly instead of redirecting
            const studentId = user.student_id;
            const student = await Student.findByPk(studentId, {
                include: [{ model: Advisor }]
            });
            
            if (!student) {
                return res.redirect('/');
            }

            const enrollments = await StudentCourseEnrollment.findAll({
                where: { student_id: studentId },
                include: [{ model: Course, attributes: ['course_id', 'course_name', 'credit_hours', 'course_desc', 'absence_limit'] }]
            });

            const enrollmentsJson = enrollments.map(e => e.toJSON());
            
            // Fetch absences
            const absences = await StudentCourseAbsences.findAll({
                where: { student_id: studentId }
            });
            const absencesMap = {};
            absences.forEach(abs => {
                absencesMap[`${abs.course_id}_${abs.semester}`] = abs.toJSON();
            });
            
            // Merge absences with enrollments
            const courseEnrollments = enrollmentsJson.map(enrollment => {
                const key = `${enrollment.course_id}_${enrollment.semester}`;
                return {
                    ...enrollment,
                    StudentCourseAbsence: absencesMap[key] || null
                };
            });

            let gpaHistory = [];
            try {
                const StudentGPAHistory = require('./models/StudentGPAHistory');
                const gpaRecords = await StudentGPAHistory.findAll({
                    where: { student_id: studentId }
                });
                
                if (gpaRecords && gpaRecords.length > 0) {
                    gpaHistory = gpaRecords.map(record => {
                        const data = record.toJSON ? record.toJSON() : record;
                        return {
                            semester: data.semester,
                            gpa: parseFloat(data.gpa || 0) 
                        };
                    });
                }
            } catch (error) {
                console.error("Could not fetch GPA history:", error.message);
            }

            const currentCourses = courseEnrollments.filter(enrollment => 
                enrollment.status === 'Current');
            const completedCourses = courseEnrollments.filter(enrollment => 
                enrollment.status === 'Completed');
            const leftoverCourses = courseEnrollments.filter(enrollment => 
                enrollment.status === 'Leftover');

            let warnings = [];
            if (student.cumulative_gpa && student.cumulative_gpa < 2.0) {
                warnings.push("Academic probation (GPA below 2.0)");
            }

            const studentData = {
                ...student.toJSON(),
                courses: courseEnrollments,
                gpaHistory: gpaHistory,
                currentCourses: currentCourses,
                completedCourses: completedCourses,
                leftoverCourses: leftoverCourses,
                warnings: warnings,
                academic_level: calculateAcademicLevel(student.completed_hours || 0),
                remaining_hours: 134 - (student.completed_hours || 0),
                viewMode: userType
            };

            return res.render('Student', { user: studentData });
        }

    } catch (err) {
        console.error('[Login] caught error:', err.stack || err);
        res.status(500).send(`[Login] Internal Server Error: ${err.message}`);
    }
});



//avisor 
app.get('/advisor/:id', async (req, res) => {
    try {
        // Check if user is logged in
        if (!req.session.userId || req.session.userType !== 'faculty') {
            return res.redirect('/');
        }
        
        const advisorId = req.params.id;
        
        // Fetch advisor data
        const advisor = await Advisor.findByPk(advisorId);
        if (!advisor) {
            return res.redirect('/');
        }
        
        // Get all students assigned to this advisor
        const allStudents = await Student.findAll({
            where: { advisor_id: advisorId },
            attributes: ['student_id', 'Fname', 'Lname', 'email']
        });
        
       
        let HighRiskStudents = [];
        
        try {
            // Correctly import the HighRiskStudents model
           
            
            // Now use the model properly
            HighRiskStudents = await HighRiskStudentsModel.findAll({
                where: { advisor_id: advisorId },
                include: [{
                    model: Student,
                    attributes: ['Fname', 'Lname', 'email']
                }]
            });
            
        } catch (error) {
            console.log("Could not query High_Risk_Students table:", error.message);
            
            try {
               
                const studentAttributes = Object.keys(Student.getAttributes);
                
                if (studentAttributes.includes('cumulative_gpa')) {
                   
                    HighRiskStudents = await Student.findAll({
                        where: { 
                            advisor_id: advisorId,
                            cumulative_gpa: { [Op.lt]: 2.0 }
                        },
                        attributes: ['student_id', 'Fname', 'Lname', 'email', 'cumulative_gpa']
                    });
                } else {
                    
                    console.log("Student model does not have cumulative_gpa column");
                    HighRiskStudents = [];
                }
            } catch (innerError) {
                console.log("Could not query students by GPA:", innerError.message);
                
                HighRiskStudents = [];
            }
        }
        
        // mock tickets
        const tickets = [
            {
                student_name: allStudents.length > 0 ? `${allStudents[0].Fname} ${allStudents[0].Lname}` : 'Student Name',
                created_at: new Date(),
                description: 'Need help with course registration'
            },
            {
                student_name: allStudents.length > 1 ? `${allStudents[1].Fname} ${allStudents[1].Lname}` : 'Another Student',
                created_at: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000), // 5 days ago
                description: 'Requesting advisor meeting for career advice'
            }
        ];
        
    
        
      
        res.render('Advisor', { 
            user: advisor,
            allStudents,
            HighRiskStudents,
            tickets
        });
        
    } catch (err) {
        console.error('Error in advisor route:', err);
        res.status(500).send('Server error');
    }
});


app.get('/student/:id', async (req, res) => {
    try {
        // Check if user is logged in 
        if (!req.session.userId) {
            return res.redirect('/');
        }
        
        const studentId = req.params.id;
        
        
        // For advisors, check if this student is assigned to them
        if (req.session.userType === 'faculty') {
           
            const student = await Student.findByPk(studentId);
            
            if (!student || student.advisor_id !== req.session.userId) {
                console.log('Advisor attempted to access non-advised student');
                return res.redirect(`/advisor/${req.session.userId}`);
            }
        }
        
        // Fetch student data
        const user = await Student.findByPk(studentId, {
            include: [
                { model: Advisor }, 
            ]
        });
        
        if (!user) {
            return res.redirect('/');
        }

        
          
      const enrollments = await StudentCourseEnrollment.findAll({
        where: { student_id: studentId },
        include: [{ model: Course, attributes: ['course_id', 'course_name', 'credit_hours', 'course_desc', 'absence_limit'] }]
    });
        
        const enrollmentsJson = enrollments.map(e => e.toJSON());
          
        // Fetch absences
        const absences = await StudentCourseAbsences.findAll({
            where: { student_id: studentId }
        });
        const absencesMap = {};
        absences.forEach(abs => {
            absencesMap[`${abs.course_id}_${abs.semester}`] = abs.toJSON();
        });
          
        // Merge absences with enrollments
        const courseEnrollments = enrollmentsJson.map(enrollment => {
            const key = `${enrollment.course_id}_${enrollment.semester}`;
            return {
                ...enrollment,
                StudentCourseAbsence: absencesMap[key] || null
            };
        });
        
          

        let gpaHistory = [];
        try {
            const StudentGPAHistory = require('./models/StudentGPAHistory');
            
            
            if (!StudentGPAHistory) {
                console.error('StudentGPAHistory model not loaded correctly');
                throw new Error('Model not loaded');
            }
            
            // Log for debugging
            console.log('StudentGPAHistory model:', StudentGPAHistory.tableName || 'No tableName property');
            
           
            const gpaRecords = await StudentGPAHistory.findAll({
                where: { student_id: studentId }
            });
            
            console.log(`Found ${gpaRecords ? gpaRecords.length : 0} GPA history records for student ${studentId}`);
            
           
            if (gpaRecords && gpaRecords.length > 0) {
                gpaHistory = gpaRecords.map(record => {
                    // Convert Sequelize model
                    const data = record.toJSON ? record.toJSON() : record;
                    return {
                        semester: data.semester,
                        gpa: parseFloat(data.gpa || 0) 
                    };
                });
            } 
            
        } catch (error) {
            console.error("Could not fetch GPA history:", error.message);
            console.error(error.stack); // Log the full stack trace for debugging
        }


        
       
        
        // 4. Check for academic warnings
        let warnings = [];
        if (user.cumulative_gpa && user.cumulative_gpa < 2.0) {
            warnings.push("Academic probation (GPA below 2.0)");
        }
        
        // If you track attendance
        if (user.attendance && user.attendance < 0.75) {
            warnings.push("Low attendance");
        }

        const currentCourses = courseEnrollments.filter(enrollment => 
            enrollment.status === 'Current');
        
        const completedCourses = courseEnrollments.filter(enrollment => 
            enrollment.status === 'Completed');
        
        const leftoverCourses = courseEnrollments.filter(enrollment => 
            enrollment.status === 'Leftover');

            console.log(`Found ${currentCourses.length} current courses`);
            console.log(`Found ${completedCourses.length} completed courses`);
            console.log(`Found ${leftoverCourses.length} leftover courses`);

 // Fetch ratings for completed courses
 if (completedCourses.length > 0) {
    // Fetch student's ratings for these courses
    const courseIds = completedCourses.map(course => course.course_id);
    const ratings = await CourseRating.findAll({
        where: {
            course_id: { [Op.in]: courseIds }
        }
    });

    // Create a map for easier lookups
    const courseRatingsMap = {};
    ratings.forEach(rating => {
        if (!courseRatingsMap[rating.course_id]) {
            courseRatingsMap[rating.course_id] = {
                total: 0,
                count: 0,
                studentRating: null
            };
        }

        courseRatingsMap[rating.course_id].total += rating.rating;
        courseRatingsMap[rating.course_id].count += 1;
        
        // Store student's own rating if available
        if (rating.student_id.toString() === studentId.toString()) {
            courseRatingsMap[rating.course_id].studentRating = rating.rating;
        }
    });

    // Enhance the completed courses with rating information
    completedCourses.forEach(course => {
        const ratingInfo = courseRatingsMap[course.course_id];
        if (ratingInfo) {
            course.avgRating = ratingInfo.count > 0 ? 
                (ratingInfo.total / ratingInfo.count).toFixed(1) : null;
            course.myRating = ratingInfo.studentRating;
        }
    });
}






        // Prepare data for the template
        const studentData = {
            ...user.toJSON(),
            courses: courseEnrollments,
            gpaHistory: gpaHistory,
            currentCourses: currentCourses,        // Add this
            completedCourses: completedCourses,    // Add this
            leftoverCourses: leftoverCourses, // This would be replaced with actual GPA history if available
            warnings: warnings,
           
            // Calculate academic info
            academic_level: calculateAcademicLevel(user.completed_hours || 0),
            remaining_hours: 134 - (user.completed_hours || 0), 
            viewMode: req.session.userType // 'student' or 'faculty'
        
        };

        // Debug log to confirm gpaHistory is included in studentData
        console.log(`studentData includes ${studentData.gpaHistory.length} GPA history records`);


        res.render('Student', { user: studentData });
        
    } catch (err) {
        console.error('Error in student route:', err);
        res.status(500).send('Server error');
    }
});

// Helper function to determine academic level based on credits
function calculateAcademicLevel(completedHours) {
    if (completedHours < 30) return 'Freshman';
    if (completedHours < 60) return 'Sophomore';
    if (completedHours < 90) return 'Junior';
    return 'Senior';
}

app.post('/courses/:courseId/rate', courseRatingController.rateAndReviewCourse);

// Get average rating for a course
app.get('/courses/:courseId/ratings', courseRatingController.getAverageCourseRating);

// Chatbot endpoint
app.post('/chatbot', async (req, res) => {
    try {
        const { prompt } = req.body;
        if (!prompt) {
            return res.status(400).json({ error: 'Prompt is required' });
        }

        console.log('Sending request to Flask backend:', prompt); // Debug log

        // Make request to Flask backend
        const response = await fetch(`${process.env.BACKEND_URL}/chatbot`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            body: JSON.stringify({ prompt })
        });

        console.log('Flask response status:', response.status); // Debug log

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        console.log('Flask response data:', data); // Debug log
        res.json({ answer: data.answer });
    } catch (error) {
        console.error('Chatbot error:', error);
        res.status(500).json({ error: error.message || 'Internal server error' });
    }
});

// Route to generate and download student report PDF
app.get('/api/student/:id/report', async (req, res) => {
  const studentId = req.params.id;
  const projectRoot = path.join(__dirname, '..');
  const pdfPath = path.join(projectRoot, `student_${studentId}_report.pdf`);
  const scriptPath = path.join(projectRoot, 'generate_report.py');

  console.log('Generating report for student:', studentId);
  console.log('PDF will be saved to:', pdfPath);
  console.log('Using script at:', scriptPath);

  // Run the Python script to generate the report
  exec(`python3 "${scriptPath}" ${studentId}`, (error, stdout, stderr) => {
    if (error) {
      console.error('Error executing Python script:', error);
      console.error('Script stderr:', stderr);
      console.error('Script stdout:', stdout);
      return res.status(500).send('Error generating report');
    }
    
    console.log('Python script output:', stdout);
    
    // Wait a short moment to ensure file is written
    setTimeout(() => {
      fs.readFile(pdfPath, (err, data) => {
        if (err) {
          console.error('Error reading PDF file:', err);
          return res.status(500).send('Report not found');
        }
        res.setHeader('Content-Type', 'application/pdf');
        res.setHeader('Content-Disposition', `attachment; filename=student_${studentId}_report.pdf`);
        res.send(data);
        // Delete the file after sending
        fs.unlink(pdfPath, (unlinkErr) => {
          if (unlinkErr) console.error('Error deleting PDF:', unlinkErr);
        });
      });
    }, 1000); // Wait 1 second to ensure file is written
  });
});

// Set up the port
const PORT = process.env.PORT || 3000;

// Start the Server
const server = app.listen(PORT, '0.0.0.0', (err) => {
    if (err) {
        console.error('Error starting server:', err);
        return;
    }
    console.log(`Server is running on port ${PORT}`);
    console.log('Access URLs:');
    console.log(`- Local: http://localhost:${PORT}`);
    console.log(`- Network: http://127.0.0.1:${PORT}`);
});

server.on('error', (err) => {
    if (err.code === 'EADDRINUSE') {
        console.error(`Port ${PORT} is already in use`);
    } else {
        console.error('Server error:', err);
    }
});

// Error handling middleware
app.use((err, req, res, next) => {
    console.error(err.stack);
    res.status(err.status || 500).json({
        error: process.env.NODE_ENV === 'development' ? err.message : 'Internal server error'
    });
});

// Handle 404s - this should be the last middleware
app.use((req, res, next) => {
    if (!res.headersSent) {
        res.status(404).json({ error: 'Not found' });
    }
});