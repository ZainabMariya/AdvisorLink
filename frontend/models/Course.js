const { DataTypes } = require('sequelize');
const sequelize = require('../config/database');
const Department = require('./Department');

const Course = sequelize.define('Course', {
  course_id: {
    type: DataTypes.STRING(10),
    primaryKey: true
  },
  course_name: {
    type: DataTypes.STRING(255),
    allowNull: false
  },
  course_desc: {
    type: DataTypes.STRING(255),
    allowNull: false
  },
  credit_hours: {
    type: DataTypes.INTEGER,
    allowNull: false
  },
  difficulty_rating: {
    type: DataTypes.FLOAT,
    allowNull: true
  },
  prerequisite_course_id: {
    type: DataTypes.STRING(50),
    allowNull: true
  },
  department_id: {
    type: DataTypes.STRING(10),
    allowNull: false
  },
  absence_limit: {
    type: DataTypes.INTEGER,
    allowNull: true,
    defaultValue: null
  }
}, {
  tableName: 'Course',
  timestamps: false,
  hooks: {
    beforeCreate: (course, options) => {
      course.absence_limit = getAbsenceLimit(course.credit_hours);
    },
    beforeUpdate: (course, options) => {
      course.absence_limit = getAbsenceLimit(course.credit_hours);
    }
  }
});

// Function to calculate absence limit based on credit hours
function getAbsenceLimit(creditHours) {
  switch (creditHours) {
    case 4: return 18;
    case 3: return 16;
    case 2: return 12;
    case 1: return 8;
    default: return null;
  }
}

// Associations
Course.belongsTo(Department, {
  foreignKey: 'department_id',
  onDelete: 'RESTRICT'
});
Department.hasMany(Course, { foreignKey: 'department_id' });

module.exports = Course;
