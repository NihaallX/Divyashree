import { useEffect, useRef, useState } from 'react'
import { motion, useScroll, useSpring } from 'framer-motion'
import Section from '../components/Section'
import Layout from '../components/Layout'
import Navbar from '../components/Navbar'
import TestCallModal from '../components/TestCallModal'
import { sections } from '../constants/sections'

export default function LandingPage() {
  const [activeSection, setActiveSection] = useState(0)
  const [isTestCallModalOpen, setIsTestCallModalOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const { scrollYProgress } = useScroll({ container: containerRef })
  const scaleX = useSpring(scrollYProgress, { stiffness: 100, damping: 30, restDelta: 0.001 })

  useEffect(() => {
    const handleScroll = () => {
      if (containerRef.current) {
        const scrollPosition = containerRef.current.scrollTop
        const windowHeight = window.innerHeight
        const newActiveSection = Math.floor(scrollPosition / windowHeight)
        setActiveSection(newActiveSection)
      }
    }

    const container = containerRef.current
    if (container) {
      container.addEventListener('scroll', handleScroll)
    }

    return () => {
      if (container) {
        container.removeEventListener('scroll', handleScroll)
      }
    }
  }, [])

  const handleNavClick = (index: number) => {
    if (containerRef.current) {
      containerRef.current.scrollTo({
        top: index * window.innerHeight,
        behavior: 'smooth'
      })
    }
  }

  return (
    <Layout>
      <Navbar />
      <TestCallModal 
        isOpen={isTestCallModalOpen} 
        onClose={() => setIsTestCallModalOpen(false)} 
      />
      <nav className="fixed top-0 right-0 h-screen flex flex-col justify-center z-30 p-4">
        {sections.map((section, index) => (
          <button
            key={section.id}
            className={`w-3 h-3 rounded-full my-2 transition-all ${
              index === activeSection ? 'bg-white scale-150' : 'bg-gray-600'
            }`}
            onClick={() => handleNavClick(index)}
            aria-label={`Go to ${section.title}`}
          />
        ))}
      </nav>
      <motion.div
        className="fixed top-0 left-0 right-0 h-0.5 bg-cyan-500 origin-left z-30"
        style={{ scaleX }}
      />
      <div 
        ref={containerRef} 
        className="h-full overflow-y-auto snap-y snap-mandatory scrollbar-hide"
      >
        {sections.map((section, index) => (
          <Section
            key={section.id}
            {...section}
            isActive={index === activeSection}
            onTestCall={() => setIsTestCallModalOpen(true)}
          />
        ))}
      </div>
    </Layout>
  )
}
